"""Incremental scan of source folders into the media table.

A file is (re)processed only when it is new or its size/mtime changed.
Files that disappeared are flagged `missing`; rows are never deleted here.
"""

import logging
import os
import threading
from datetime import datetime
from pathlib import Path

from PIL import Image
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import PHOTO_EXTS, THUMB_MAX_EDGE
from ..db import SessionLocal
from ..models import Media, ScanJob, SourceFolder
from ..safety import open_source
from .dates import detect_date
from .metadata import read_image_info, sha256_file
from .thumbs import make_thumbnail, save_thumbnail
from .video import read_creation_time, read_video
from .walker import iter_media_files

log = logging.getLogger(__name__)

COMMIT_EVERY = 25


def process_file(session: Session, media: Media, path: Path, st: os.stat_result) -> None:
    """Fill `media` from the file at `path` and write its thumbnail. Reads the original only."""
    ext = path.suffix.lower()
    media.filename = path.name
    media.ext = ext
    media.kind = "photo" if ext in PHOTO_EXTS else "video"
    media.size = st.st_size
    media.mtime_ns = st.st_mtime_ns
    media.scanned_at = datetime.now()
    media.missing = False
    media.has_thumb = False
    media.width = media.height = media.duration_s = media.orientation = None
    media.gps_lat = media.gps_lon = media.camera = None
    media.sha256 = None
    problems: list[str] = []

    try:
        media.sha256 = sha256_file(path)
    except OSError as e:
        problems.append(f"hash failed: {e}")

    exif_dt = video_dt = None
    thumb: Image.Image | None = None

    if media.kind == "photo":
        try:
            with open_source(path) as f, Image.open(f) as img:
                info = read_image_info(img)
                media.width, media.height = info.width, info.height
                media.orientation = info.orientation
                media.camera = info.camera
                media.gps_lat, media.gps_lon = info.gps_lat, info.gps_lon
                exif_dt = info.exif_datetime
                img.draft("RGB", (THUMB_MAX_EDGE * 2, THUMB_MAX_EDGE * 2))  # fast JPEG decode
                thumb = make_thumbnail(img)
        except Exception as e:
            problems.append(f"could not read image: {e}")
    else:
        video_dt = read_creation_time(path)
        try:
            vinfo = read_video(path)
        except Exception as e:
            vinfo = None
            problems.append(f"could not read video: {e}")
        if vinfo is None:
            problems.append("could not decode video frames for thumbnail")
        else:
            media.width, media.height, media.duration_s = vinfo.width, vinfo.height, vinfo.duration_s
            if vinfo.frame is not None:
                thumb = make_thumbnail(vinfo.frame)

    date = detect_date(path.name, st.st_mtime, exif_value=exif_dt, video_created=video_dt)
    media.taken_at = date.taken_at
    media.date_source = date.source
    media.date_confidence = date.confidence

    session.add(media)
    session.flush()  # assigns media.id for the thumbnail filename

    if thumb is not None:
        try:
            save_thumbnail(thumb, media.id)
            media.has_thumb = True
        except Exception as e:
            problems.append(f"thumbnail failed: {e}")

    media.error = "; ".join(problems) or None


def create_job(session: Session, folder_id: int | None = None, kind: str = "scan") -> ScanJob:
    job = ScanJob(folder_id=folder_id, kind=kind)
    session.add(job)
    session.commit()
    return job


def run_scan(job_id: int, cancel: threading.Event | None = None) -> ScanJob:
    """Run a scan job to completion in the calling thread."""
    with SessionLocal() as s:
        job = s.get(ScanJob, job_id)
        job.status = "running"
        job.started_at = datetime.now()
        s.commit()

        try:
            _scan(s, job, cancel)
        except Exception as e:
            log.exception("Scan %s failed", job_id)
            s.rollback()
            job = s.get(ScanJob, job_id)
            job.status = "failed"
            job.message = str(e)
        job.finished_at = datetime.now()
        s.commit()
        return job


def _scan(s: Session, job: ScanJob, cancel: threading.Event | None) -> None:
    q = select(SourceFolder).where(SourceFolder.enabled)
    if job.folder_id is not None:
        q = q.where(SourceFolder.id == job.folder_id)
    folders = s.scalars(q).all()

    # Pass 1: discover files (so the UI can show a total)
    work: list[tuple[SourceFolder, Path, Path]] = []
    scanned_folders: list[SourceFolder] = []
    notes: list[str] = []
    for folder in folders:
        root = Path(folder.path)
        if not root.is_dir():
            # Drive unplugged or folder renamed: leave its media untouched
            notes.append(f"Folder not found, skipped: {folder.path}")
            continue
        scanned_folders.append(folder)
        work.extend((folder, root, p) for p in iter_media_files(root))
    job.total = len(work)
    job.message = "\n".join(notes) or None
    s.commit()

    # Lightweight index of what is already known: (folder_id, rel_path) -> (id, size, mtime_ns, missing)
    known: dict[tuple[int, str], tuple[int, int, int, bool]] = {}
    for folder in scanned_folders:
        rows = s.execute(
            select(Media.id, Media.rel_path, Media.size, Media.mtime_ns, Media.missing).where(
                Media.folder_id == folder.id
            )
        )
        for mid, rel, size, mtime_ns, missing in rows:
            known[(folder.id, rel)] = (mid, size, mtime_ns, missing)

    seen: set[tuple[int, str]] = set()
    revived: list[int] = []

    # Pass 2: process new/changed files
    for i, (folder, root, path) in enumerate(work, start=1):
        if cancel is not None and cancel.is_set():
            job.status = "cancelled"
            s.commit()
            return

        rel = path.relative_to(root).as_posix()
        key = (folder.id, rel)
        seen.add(key)
        try:
            st = path.stat()
            prev = known.get(key)
            if prev and prev[1] == st.st_size and prev[2] == st.st_mtime_ns:
                job.unchanged += 1
                if prev[3]:
                    revived.append(prev[0])
            else:
                media = s.get(Media, prev[0]) if prev else Media(folder_id=folder.id, rel_path=rel)
                process_file(s, media, path, st)
                if media.error:
                    job.errors += 1
                if prev:
                    job.updated += 1
                else:
                    job.added += 1
        except OSError as e:  # vanished or unreadable between discovery and processing
            log.warning("Skipped %s: %s", path, e)
            job.errors += 1
        except Exception as e:  # database-level failure: drop uncommitted batch, keep going
            log.exception("Failed to process %s", path)
            s.rollback()
            job = s.get(ScanJob, job.id)
            job.errors += 1

        job.processed = i
        if i % COMMIT_EVERY == 0:
            s.commit()

    if revived:
        s.execute(update(Media).where(Media.id.in_(revived)).values(missing=False))

    gone = [v[0] for k, v in known.items() if k not in seen and not v[3]]
    if gone:
        s.execute(update(Media).where(Media.id.in_(gone)).values(missing=True))
    job.missing = len(gone)

    now = datetime.now()
    for folder in scanned_folders:
        folder.last_scanned_at = now
    job.status = "done"
    s.commit()
