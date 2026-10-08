from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import ScanJob, SourceFolder
from ..scanner.jobs import ACTIVE, manager

router = APIRouter(prefix="/api/scan", tags=["scan"])


class ScanIn(BaseModel):
    folder_id: int | None = None


def job_dict(job: ScanJob | None) -> dict | None:
    if job is None:
        return None
    return {
        c: getattr(job, c)
        for c in (
            "id", "kind", "status", "folder_id", "created_at", "started_at", "finished_at", "total",
            "processed", "added", "updated", "unchanged", "missing", "errors", "message",
        )
    }


@router.post("", status_code=202)
def start_scan(body: ScanIn | None = None, s: Session = Depends(get_session)):
    folder_id = body.folder_id if body else None
    if folder_id is not None and not s.get(SourceFolder, folder_id):
        raise HTTPException(404, "Folder not found")
    if not s.scalars(select(SourceFolder).where(SourceFolder.enabled)).first():
        raise HTTPException(400, "Add a photo folder first.")
    return job_dict(manager.enqueue(folder_id))


@router.get("/status")
def scan_status(s: Session = Depends(get_session)):
    active = s.scalars(select(ScanJob).where(ScanJob.status.in_(ACTIVE)).order_by(ScanJob.id)).first()
    last = s.scalars(
        select(ScanJob).where(~ScanJob.status.in_(ACTIVE)).order_by(ScanJob.id.desc())
    ).first()
    return {"active": job_dict(active), "last": job_dict(last)}


@router.post("/cancel")
def cancel_scan():
    manager.cancel()
    return {"ok": True}
