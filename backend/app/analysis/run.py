"""Analysis job: pHash, quality, CLIP and faces for new/changed photos;
then regroup duplicates, cluster people, tag scenes and rebuild events."""

import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import settings_store
from ..ai import registry
from ..db import SessionLocal
from ..models import ClipEmbedding, Face, Media, Quality, ScanJob, SourceFolder
from ..events.build import rebuild_events
from ..events.tags import tag_all
from ..people.cluster import cluster_faces
from ..people.crops import delete_crop, make_crop, save_crop
from ..safety import open_source
from . import quality as q
from .grouping import regroup
from .phash import phash

log = logging.getLogger(__name__)

ANALYSIS_VERSION = 2
ANALYSIS_EDGE = 1024  # quality metrics, pHash, CLIP
FACE_EDGE = 1600  # face detection/recognition and crops
JUDGE_FACE_PX = 80  # faces at least this wide (at FACE_EDGE) get an eyes-open verdict
COMMIT_EVERY = 10

try:  # quieten OpenCV DNN backend notices
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
except AttributeError:
    pass


@dataclass
class FaceRecord:
    box: tuple[float, float, float, float]  # normalised x, y, w, h
    landmarks: list[list[float]]  # normalised
    det_score: float
    size_px: int
    quality: float
    eyes_open: bool | None
    embedding: np.ndarray
    crop: Image.Image


@dataclass
class Analysis:
    phash: str
    quality: dict
    embedding: np.ndarray | None
    faces: list[FaceRecord] | None  # None = no face model installed


class Analyzer:
    """Loads whichever local models are installed; works (with fewer signals) without them."""

    def __init__(self) -> None:
        self.insight = None
        self.faces = None
        if registry.is_installed("buffalo_l"):
            from ..ai.insightface import FaceEngine

            self.insight = FaceEngine()
            self.eyes = q.EyeChecker()
        elif registry.is_installed("yunet"):
            self.faces = q.FaceAnalyzer()
        self.clip = None
        if registry.is_installed("clip_vision"):
            from ..ai.clip import ClipScorer

            self.clip = ClipScorer()
        used = []
        if self.insight:
            used.append("insightface")
        elif self.faces:
            used.append("yunet")
        if self.clip:
            used.append("clip")
            if self.clip.head is not None:
                used.append("aesthetic")
        self.models_used = ",".join(used)

    def _insight_faces(self, big: Image.Image) -> tuple[list[FaceRecord], q.FaceResult]:
        rgb = np.asarray(big)
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        W, H = big.size
        records, result = [], q.FaceResult()
        open_flags, sharp = [], []
        for f in self.insight.analyze(bgr):
            x1, y1, x2, y2 = (float(v) for v in f.box)
            size = int(x2 - x1)
            face_sharp = q.sharpness_score(q.sharpness_raw(cv2.cvtColor(f.aligned, cv2.COLOR_BGR2GRAY)))
            det = min(1.0, max(0.0, (f.score - 0.5) / 0.4))
            size_f = min(1.0, max(0.0, (size - 24) / 88))
            quality = 0.0 if size < 24 else round(0.4 * det + 0.3 * size_f + 0.3 * face_sharp, 3)
            eyes = None
            if size >= JUDGE_FACE_PX:
                eyes = self.eyes.eyes_open(gray, f.kps, size)
                open_flags.append(eyes)
                sharp.append(face_sharp)
            records.append(
                FaceRecord(
                    box=(x1 / W, y1 / H, (x2 - x1) / W, (y2 - y1) / H),
                    landmarks=[[round(float(px) / W, 4), round(float(py) / H, 4)] for px, py in f.kps],
                    det_score=round(f.score, 3),
                    size_px=size,
                    quality=quality,
                    eyes_open=eyes,
                    embedding=f.embedding,
                    crop=make_crop(big, (x1, y1, x2, y2)),
                )
            )
        result.count = len(records)
        result.judged = len(open_flags)
        if open_flags:
            result.eyes_open = sum(open_flags) / len(open_flags)
            result.face_sharpness = float(np.mean(sharp))
        return records, result

    def analyze(self, path: Path, width: int, height: int) -> Analysis:
        with open_source(path) as f, Image.open(f) as im:
            im.draft("RGB", (FACE_EDGE, FACE_EDGE))
            big = ImageOps.exif_transpose(im).convert("RGB")
        big.thumbnail((FACE_EDGE, FACE_EDGE), Image.Resampling.LANCZOS)
        img = big.copy()
        img.thumbnail((ANALYSIS_EDGE, ANALYSIS_EDGE), Image.Resampling.LANCZOS)
        rgb = np.asarray(img)
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

        sharp_raw = q.sharpness_raw(gray)
        comp: dict = {
            "sharpness_raw": sharp_raw,
            "sharpness": q.sharpness_score(sharp_raw),
            "exposure": q.exposure_score(gray),
            "resolution": q.resolution_score(width or big.width, height or big.height),
            "faces": 0,
            "face_score": None,
            "eyes_open": None,
            "aesthetic_raw": None,
            "aesthetic": None,
        }
        face_records = None
        fr = None
        if self.insight:
            face_records, fr = self._insight_faces(big)
        elif self.faces:
            fr = self.faces.analyze(bgr, gray)
        if fr is not None:
            comp.update(faces=fr.count, face_score=fr.score, eyes_open=fr.eyes_open)
            if fr.face_sharpness is not None:  # judge sharpness on the subject, not the background
                comp["sharpness"] = max(comp["sharpness"], fr.face_sharpness)

        embedding = None
        if self.clip:
            from ..ai.clip import aesthetic_score

            embedding = self.clip.embed(img)
            raw = self.clip.aesthetic(embedding)
            if raw is not None:
                comp.update(aesthetic_raw=raw, aesthetic=aesthetic_score(raw))

        comp["total"] = q.total_score(
            {
                "sharpness": comp["sharpness"],
                "exposure": comp["exposure"],
                "resolution": comp["resolution"],
                "face": comp["face_score"],
                "aesthetic": comp["aesthetic"],
            }
        )
        return Analysis(phash=phash(gray), quality=comp, embedding=embedding, faces=face_records)


def _iou(a: tuple, b: tuple) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    return inter / union if union else 0.0


def store_faces(s: Session, media_id: int, records: list[FaceRecord]) -> None:
    """Replace a photo's faces, carrying over people/corrections to the matching new boxes."""
    old = s.scalars(select(Face).where(Face.media_id == media_id)).all()
    new_rows = []
    for rec in records:
        row = Face(
            media_id=media_id,
            x=rec.box[0], y=rec.box[1], w=rec.box[2], h=rec.box[3],
            landmarks=json.dumps(rec.landmarks),
            det_score=rec.det_score,
            size_px=rec.size_px,
            quality=rec.quality,
            eyes_open=rec.eyes_open,
            embedding=rec.embedding.astype(np.float32).tobytes(),
        )
        match = max(old, key=lambda o: _iou((o.x, o.y, o.w, o.h), rec.box), default=None)
        if match is not None and _iou((match.x, match.y, match.w, match.h), rec.box) >= 0.5:
            row.person_id, row.assigned_by, row.not_person_ids = (
                match.person_id, match.assigned_by, match.not_person_ids,
            )
        new_rows.append(row)
    for o in old:
        delete_crop(o.id)
        s.delete(o)
    s.flush()
    s.add_all(new_rows)
    s.flush()
    for row, rec in zip(new_rows, records):
        save_crop(rec.crop, row.id)

def _needs_analysis(m: Media, qual: Quality | None, models_used: str) -> bool:
    return (
        qual is None
        or m.phash is None
        or qual.version != ANALYSIS_VERSION
        or qual.media_mtime_ns != m.mtime_ns
        or qual.models_used != models_used
    )


def regroup_from_settings(s: Session) -> dict:
    cfg = settings_store.get_all(s)
    return regroup(s, cfg["near_dup_threshold"], cfg["burst_threshold"], cfg["burst_enabled"])


def run_analysis(job_id: int, cancel: threading.Event | None = None) -> ScanJob:
    with SessionLocal() as s:
        job = s.get(ScanJob, job_id)
        job.status, job.started_at = "running", datetime.now()
        s.commit()
        try:
            _analyze(s, job, cancel)
        except Exception as e:
            log.exception("Analysis %s failed", job_id)
            s.rollback()
            job = s.get(ScanJob, job_id)
            job.status, job.message = "failed", str(e)
        job.finished_at = datetime.now()
        s.commit()
        return job


def _analyze(s: Session, job: ScanJob, cancel: threading.Event | None) -> None:
    analyzer = Analyzer()
    roots = dict(s.execute(select(SourceFolder.id, SourceFolder.path)).all())
    rows = s.execute(
        select(Media, Quality)
        .outerjoin(Quality, Quality.media_id == Media.id)
        .where(Media.kind == "photo", ~Media.missing, Media.has_thumb)
        .order_by(Media.taken_at)
    ).all()
    todo = [(m, qual) for m, qual in rows if _needs_analysis(m, qual, analyzer.models_used)]
    job.total, job.unchanged = len(todo), len(rows) - len(todo)
    s.commit()

    for i, (m, qual) in enumerate(todo, start=1):
        if cancel is not None and cancel.is_set():
            job.status = "cancelled"
            s.commit()
            return
        path = Path(roots[m.folder_id]) / m.rel_path
        try:
            result = analyzer.analyze(path, m.width, m.height)
        except Exception as e:
            log.warning("Could not analyze %s: %s", path, e)
            job.errors += 1
        else:
            m.phash = result.phash
            if qual is None:
                qual = Quality(media_id=m.id)
                s.add(qual)
            for key, value in result.quality.items():
                setattr(qual, key, value)
            qual.version = ANALYSIS_VERSION
            qual.media_mtime_ns = m.mtime_ns
            qual.models_used = analyzer.models_used
            qual.analyzed_at = datetime.now()
            if result.embedding is not None:
                emb = s.get(ClipEmbedding, m.id) or ClipEmbedding(media_id=m.id)
                emb.model, emb.vector = "clip-vit-b32", result.embedding.astype(np.float32).tobytes()
                s.add(emb)
            if result.faces is not None:
                store_faces(s, m.id, result.faces)
            job.updated += 1
        job.processed = i
        if i % COMMIT_EVERY == 0:
            s.commit()
    s.commit()

    summary = regroup_from_settings(s)
    notes = [f"{summary['groups']} duplicate groups, {summary['hidden']} extra copies hidden"]
    if analyzer.insight:
        people = cluster_faces(s)
        notes.append(
            f"{people['new_people']} new people found, {people['assigned']} faces sorted, "
            f"{people['unassigned']} faces not yet recognised"
        )
    tagged = tag_all(s, settings_store.get_all(s)["tag_threshold"])
    if "photos" in tagged:
        notes.append(f"{tagged['tagged']} photos got scene tags")
    events = rebuild_events(s)
    notes.append(f"{events['events']} events")
    status = registry.status()
    if status["buffalo_l"]["installed"]:
        status.pop("yunet")  # only a fallback
    missing = [k for k, v in status.items() if not v["installed"]]
    if missing:
        notes.append("AI models not installed: " + ", ".join(missing))
    job.message = "\n".join(notes)
    job.status = "done"
    s.commit()
