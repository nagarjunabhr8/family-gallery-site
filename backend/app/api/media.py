import io
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from PIL import Image, ImageOps
from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import DupGroup, DupMember, Event, EventMedia, Face, Media, MediaTag, Person, Quality, SourceFolder
from ..safety import is_inside, open_source
from ..scanner.thumbs import thumb_path

router = APIRouter(prefix="/api", tags=["media"])

BROWSER_SAFE_PHOTOS = {".jpg", ".jpeg", ".png", ".webp"}
MEDIA_TYPES = {".mp4": "video/mp4", ".mov": "video/quicktime"}


def summary(m: Media) -> dict:
    return {
        "id": m.id,
        "filename": m.filename,
        "kind": m.kind,
        "taken_at": m.taken_at,
        "date_source": m.date_source,
        "date_confidence": m.date_confidence,
        "width": m.width,
        "height": m.height,
        "duration_s": m.duration_s,
        "has_thumb": m.has_thumb,
        "rotation": m.user_rotation,
        "error": m.error,
    }


def quality_dict(q: Quality | None) -> dict | None:
    if q is None:
        return None
    return {
        "total": q.total,
        "sharpness": round(q.sharpness, 3),
        "exposure": round(q.exposure, 3),
        "resolution": round(q.resolution, 3),
        "faces": q.faces,
        "face_score": q.face_score,
        "eyes_open": q.eyes_open,
        "aesthetic": q.aesthetic,
        "aesthetic_raw": round(q.aesthetic_raw, 2) if q.aesthetic_raw is not None else None,
    }


def hidden_duplicates():
    """Media ids that are in a duplicate group but are not its best photo."""
    return (
        select(DupMember.media_id)
        .join(DupGroup, DupGroup.id == DupMember.group_id)
        .where(DupGroup.best_media_id != DupMember.media_id)
    )


def group_info(s: Session, media_ids: list[int]) -> dict[int, tuple[int, int]]:
    """media_id -> (group_id, group size) for the given ids."""
    if not media_ids:
        return {}
    rows = s.execute(
        select(DupMember.media_id, DupGroup.id, DupGroup.size)
        .join(DupGroup, DupGroup.id == DupMember.group_id)
        .where(DupMember.media_id.in_(media_ids))
    ).all()
    return {mid: (gid, size) for mid, gid, size in rows}


@router.get("/media")
def list_media(
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
    kind: Literal["photo", "video"] | None = None,
    date_source: Literal["exif", "video_meta", "filename", "mtime"] | None = None,
    year: int | None = None,
    order: Literal["asc", "desc"] = "desc",
    include_duplicates: bool = False,
    tag: str | None = None,
    s: Session = Depends(get_session),
):
    q = select(Media).where(~Media.missing)
    if tag:
        q = q.where(Media.id.in_(select(MediaTag.media_id).where(MediaTag.tag == tag)))
    if not include_duplicates:
        q = q.where(Media.id.not_in(hidden_duplicates()))
    if kind:
        q = q.where(Media.kind == kind)
    if date_source:
        q = q.where(Media.date_source == date_source)
    if year:
        q = q.where(extract("year", Media.taken_at) == year)
    total = s.scalar(select(func.count()).select_from(q.subquery()))
    sort = Media.taken_at.asc() if order == "asc" else Media.taken_at.desc()
    rows = s.scalars(q.order_by(sort, Media.id).offset(offset).limit(limit)).all()
    groups = group_info(s, [m.id for m in rows])
    items = []
    for m in rows:
        gid, size = groups.get(m.id, (None, 1))
        items.append({**summary(m), "group_id": gid, "group_size": size})
    return {"total": total, "offset": offset, "items": items}


@router.get("/stats")
def stats(s: Session = Depends(get_session)):
    live = ~Media.missing
    by_kind = dict(s.execute(select(Media.kind, func.count()).where(live).group_by(Media.kind)).all())
    by_source = dict(
        s.execute(select(Media.date_source, func.count()).where(live).group_by(Media.date_source)).all()
    )
    year = extract("year", Media.taken_at)
    by_year = [
        {"year": int(y), "count": c}
        for y, c in s.execute(select(year, func.count()).where(live).group_by(year).order_by(year)).all()
    ]
    return {
        "total": sum(by_kind.values()),
        "photos": by_kind.get("photo", 0),
        "videos": by_kind.get("video", 0),
        "by_date_source": by_source,
        "by_year": by_year,
        "with_errors": s.scalar(select(func.count()).where(live, Media.error.is_not(None))),
        "missing": s.scalar(select(func.count()).where(Media.missing)),
        "duplicate_groups": s.scalar(select(func.count()).select_from(DupGroup)),
        "hidden_duplicates": s.scalar(select(func.count()).select_from(hidden_duplicates().subquery())),
    }


def _get_media(s: Session, media_id: int) -> tuple[Media, Path]:
    m = s.get(Media, media_id)
    if not m:
        raise HTTPException(404, "Not found")
    folder = s.get(SourceFolder, m.folder_id)
    path = Path(folder.path) / m.rel_path
    if not is_inside(path, folder.path):
        raise HTTPException(400, "Invalid path")
    return m, path


def _event_of(s: Session, media_id: int) -> dict | None:
    e = s.scalars(
        select(Event).join(EventMedia, EventMedia.event_id == Event.id).where(EventMedia.media_id == media_id)
    ).first()
    if e is None:
        return None
    from .events import Presenter

    d = Presenter(s, [e.id]).summary(e)
    return {"id": e.id, "title": d["title"], "date_text": d["date_text"]}


@router.get("/media/{media_id}")
def media_detail(media_id: int, s: Session = Depends(get_session)):
    m, path = _get_media(s, media_id)
    gid, size = group_info(s, [m.id]).get(m.id, (None, 1))
    faces = s.execute(
        select(Face, Person.name, Person.hidden)
        .outerjoin(Person, Person.id == Face.person_id)
        .where(Face.media_id == m.id)
        .order_by(Face.x)
    ).all()
    return {
        **summary(m),
        "group_id": gid,
        "group_size": size,
        "faces": [
            {
                "id": f.id, "x": f.x, "y": f.y, "w": f.w, "h": f.h,
                "person_id": f.person_id, "person_name": name, "person_hidden": bool(hidden),
            }
            for f, name, hidden in faces
        ],
        "quality": quality_dict(s.get(Quality, m.id)),
        "tags": [
            {"tag": t, "score": sc}
            for t, sc in s.execute(
                select(MediaTag.tag, MediaTag.score).where(MediaTag.media_id == m.id).order_by(MediaTag.score.desc())
            )
        ],
        "event": _event_of(s, m.id),
        "path": str(path),
        "size": m.size,
        "camera": m.camera,
        "gps_lat": m.gps_lat,
        "gps_lon": m.gps_lon,
        "sha256": m.sha256,
        "missing": m.missing,
        "scanned_at": m.scanned_at,
    }


@router.get("/media/{media_id}/thumb")
def media_thumb(media_id: int):
    p = thumb_path(media_id)
    if not p.is_file():
        raise HTTPException(404, "No thumbnail")
    return FileResponse(p, media_type="image/webp", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/media/{media_id}/original")
def media_original(media_id: int, s: Session = Depends(get_session)):
    """Stream the original (read-only). HEIC is converted in memory to JPEG for browsers."""
    m, path = _get_media(s, media_id)
    if not path.is_file():
        raise HTTPException(404, "Original file not found on disk")
    if m.kind == "video" or m.ext in BROWSER_SAFE_PHOTOS:
        return FileResponse(path, media_type=MEDIA_TYPES.get(m.ext))
    with open_source(path) as f, Image.open(f) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((2560, 2560))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=88)
    return Response(buf.getvalue(), media_type="image/jpeg")
