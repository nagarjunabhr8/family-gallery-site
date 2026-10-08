from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import settings_store
from ..ai import registry
from ..analysis.grouping import set_best
from ..analysis.run import regroup_from_settings
from ..db import get_session
from ..models import DupGroup, DupMember, Media, Quality, ScanJob
from ..scanner.jobs import ACTIVE, manager
from .media import quality_dict, summary
from .scan import job_dict

router = APIRouter(prefix="/api", tags=["duplicates"])


def group_dict(s: Session, g: DupGroup) -> dict:
    rows = s.execute(
        select(Media, Quality, DupMember.distance)
        .join(DupMember, DupMember.media_id == Media.id)
        .outerjoin(Quality, Quality.media_id == Media.id)
        .where(DupMember.group_id == g.id)
    ).all()
    members = [
        {
            **summary(m),
            "size": m.size,
            "rel_path": m.rel_path,
            "is_best": m.id == g.best_media_id,
            "pinned": m.pinned_best,
            "distance": dist,
            "quality": quality_dict(q),
        }
        for m, q, dist in rows
    ]
    members.sort(key=lambda x: (not x["is_best"], -(x["quality"] or {}).get("total", 0), x["id"]))
    user_chosen = any(x["pinned"] and x["is_best"] for x in members)
    return {
        "id": g.id,
        "kind": g.kind,
        "size": g.size,
        "taken_at": g.taken_at,
        "best_media_id": g.best_media_id,
        "user_chosen": user_chosen,
        "members": members,
    }


@router.get("/groups")
def list_groups(
    kind: Literal["exact", "near", "burst"] | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=200),
    s: Session = Depends(get_session),
):
    q = select(DupGroup)
    if kind:
        q = q.where(DupGroup.kind == kind)
    total = s.scalar(select(func.count()).select_from(q.subquery()))
    counts = dict(s.execute(select(DupGroup.kind, func.count()).group_by(DupGroup.kind)).all())
    groups = s.scalars(q.order_by(DupGroup.taken_at.desc(), DupGroup.id).offset(offset).limit(limit)).all()
    return {"total": total, "counts": counts, "groups": [group_dict(s, g) for g in groups]}


class BestIn(BaseModel):
    media_id: int | None = None  # None = let the app choose automatically


@router.post("/groups/{group_id}/best")
def choose_best(group_id: int, body: BestIn, s: Session = Depends(get_session)):
    g = s.get(DupGroup, group_id)
    if not g:
        raise HTTPException(404, "Group not found")
    try:
        g = set_best(s, g, body.media_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return group_dict(s, g)


class SettingsIn(BaseModel):
    near_dup_threshold: int | None = Field(None, ge=0, le=32)
    burst_threshold: int | None = Field(None, ge=0, le=40)
    burst_enabled: bool | None = None


@router.get("/settings")
def get_settings(s: Session = Depends(get_session)):
    return settings_store.get_all(s)


@router.put("/settings")
def put_settings(body: SettingsIn, s: Session = Depends(get_session)):
    if s.scalars(select(ScanJob).where(ScanJob.status.in_(ACTIVE))).first():
        raise HTTPException(409, "Please wait for the current scan/analysis to finish.")
    values = settings_store.update(s, body.model_dump(exclude_none=True))
    return {"settings": values, "regroup": regroup_from_settings(s)}


@router.post("/analyze", status_code=202)
def analyze():
    return job_dict(manager.enqueue(kind="analyze"))


@router.get("/ai/status")
def ai_status():
    return registry.status()
