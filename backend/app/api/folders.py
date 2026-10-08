import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..analysis.run import regroup_from_settings
from ..events.build import rebuild_events
from ..db import get_session
from ..models import Face, Media, ScanJob, SourceFolder
from ..people.cluster import cleanup as cleanup_people
from ..people.crops import delete_crop
from ..safety import data_dir, is_inside
from ..scanner.jobs import ACTIVE
from ..scanner.thumbs import delete_thumbnail

router = APIRouter(prefix="/api/folders", tags=["folders"])


class FolderIn(BaseModel):
    path: str


def folder_dict(folder: SourceFolder, media_count: int = 0) -> dict:
    return {
        "id": folder.id,
        "path": folder.path,
        "enabled": folder.enabled,
        "added_at": folder.added_at,
        "last_scanned_at": folder.last_scanned_at,
        "exists": Path(folder.path).is_dir(),
        "media_count": media_count,
    }


@router.get("")
def list_folders(s: Session = Depends(get_session)):
    counts = dict(
        s.execute(
            select(Media.folder_id, func.count()).where(~Media.missing).group_by(Media.folder_id)
        ).all()
    )
    folders = s.scalars(select(SourceFolder).order_by(SourceFolder.added_at)).all()
    return [folder_dict(f, counts.get(f.id, 0)) for f in folders]


@router.post("", status_code=201)
def add_folder(body: FolderIn, s: Session = Depends(get_session)):
    raw = os.path.expandvars(os.path.expanduser(body.path.strip().strip('"').strip()))
    if not raw:
        raise HTTPException(400, "Please enter a folder path.")
    path = Path(raw)
    if not path.is_absolute():
        raise HTTPException(400, "Please enter a full path, e.g. D:\\Photos\\Family")
    if not path.is_dir():
        raise HTTPException(400, f"Folder not found: {path}")
    path = path.resolve()

    if is_inside(path, data_dir()):
        raise HTTPException(400, "That folder is inside the app's own data folder.")
    for existing in s.scalars(select(SourceFolder)).all():
        if is_inside(path, existing.path):
            raise HTTPException(409, f"Already covered by {existing.path}")
        if is_inside(existing.path, path):
            raise HTTPException(
                409, f"This contains an existing folder ({existing.path}). Remove that one first."
            )

    folder = SourceFolder(path=str(path))
    s.add(folder)
    s.commit()
    return folder_dict(folder)


@router.delete("/{folder_id}")
def remove_folder(folder_id: int, s: Session = Depends(get_session)):
    """Forget a folder: removes its rows and thumbnails from the data folder. Originals untouched."""
    folder = s.get(SourceFolder, folder_id)
    if not folder:
        raise HTTPException(404, "Folder not found")
    if s.scalars(select(ScanJob).where(ScanJob.status.in_(ACTIVE))).first():
        raise HTTPException(409, "A scan is running. Cancel it or wait until it finishes.")

    media_ids = s.scalars(select(Media.id).where(Media.folder_id == folder_id)).all()
    for mid in media_ids:
        delete_thumbnail(mid)
    for fid in s.scalars(select(Face.id).join(Media, Media.id == Face.media_id).where(Media.folder_id == folder_id)):
        delete_crop(fid)
    s.execute(delete(Media).where(Media.folder_id == folder_id))
    s.delete(folder)
    s.commit()
    regroup_from_settings(s)
    cleanup_people(s)
    s.commit()
    rebuild_events(s)
    return {"removed": folder_id, "media_forgotten": len(media_ids)}
