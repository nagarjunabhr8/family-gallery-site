from datetime import date

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Face, Media, Person, ScanJob
from ..people.age import age_label
from ..people.cluster import merge_people, reassign_faces, recluster_unnamed
from ..people.crops import crop_path
from ..scanner.jobs import ACTIVE
from .media import hidden_duplicates, summary

router = APIRouter(prefix="/api", tags=["people"])


def _person_stats(s: Session) -> dict[int, dict]:
    rows = s.execute(
        select(
            Face.person_id,
            func.count(Face.id),
            func.count(func.distinct(Face.media_id)),
            func.min(Media.taken_at),
            func.max(Media.taken_at),
        )
        .join(Media, Media.id == Face.media_id)
        .where(Face.person_id.is_not(None), ~Media.missing, Media.id.not_in(hidden_duplicates()))
        .group_by(Face.person_id)
    ).all()
    return {
        pid: {"face_count": fc, "photo_count": pc, "first_taken": first, "last_taken": last}
        for pid, fc, pc, first, last in rows
    }


def person_dict(p: Person, stats: dict | None = None) -> dict:
    stats = stats or {"face_count": 0, "photo_count": 0, "first_taken": None, "last_taken": None}
    return {
        "id": p.id,
        "name": p.name,
        "birth_date": p.birth_date,
        "hidden": p.hidden,
        "cover_face_id": p.cover_face_id,
        **stats,
    }


def _get_person(s: Session, person_id: int) -> Person:
    p = s.get(Person, person_id)
    if not p:
        raise HTTPException(404, "Person not found")
    return p


def _require_idle(s: Session) -> None:
    if s.scalars(select(ScanJob).where(ScanJob.status.in_(ACTIVE))).first():
        raise HTTPException(409, "Please wait for the current scan/analysis to finish.")


@router.get("/people")
def list_people(include_hidden: bool = False, s: Session = Depends(get_session)):
    stats = _person_stats(s)
    q = select(Person)
    if not include_hidden:
        q = q.where(~Person.hidden)
    people = [person_dict(p, stats.get(p.id)) for p in s.scalars(q)]
    people.sort(key=lambda p: (p["name"] is None, -p["photo_count"], p["name"] or ""))
    unassigned = s.scalar(
        select(func.count()).select_from(Face).join(Media, Media.id == Face.media_id)
        .where(Face.person_id.is_(None), ~Media.missing)
    )
    hidden = s.scalar(select(func.count()).select_from(Person).where(Person.hidden))
    return {"people": people, "unassigned_faces": unassigned, "hidden_people": hidden}


@router.get("/people/{person_id}")
def get_person(person_id: int, s: Session = Depends(get_session)):
    p = _get_person(s, person_id)
    rows = s.execute(
        select(Media, Face.id)
        .join(Face, Face.media_id == Media.id)
        .where(Face.person_id == p.id, ~Media.missing, Media.id.not_in(hidden_duplicates()))
        .order_by(Media.taken_at, Media.id)
    ).all()
    photos, seen = [], set()
    for m, face_id in rows:
        if m.id in seen:  # same person detected twice in one photo
            continue
        seen.add(m.id)
        photos.append({**summary(m), "face_id": face_id, "age": age_label(p.birth_date, m.taken_at.date())})
    return {**person_dict(p, _person_stats(s).get(p.id)), "photos": photos}


class PersonPatch(BaseModel):
    name: str | None = None
    birth_date: date | None = None
    hidden: bool | None = None


@router.patch("/people/{person_id}")
def update_person(person_id: int, body: PersonPatch, s: Session = Depends(get_session)):
    p = _get_person(s, person_id)
    fields = body.model_fields_set
    if "name" in fields:
        p.name = (body.name or "").strip() or None
    if "birth_date" in fields:
        p.birth_date = body.birth_date
    if "hidden" in fields and body.hidden is not None:
        p.hidden = body.hidden
    s.commit()
    if fields & {"name", "birth_date", "hidden"}:  # birthdays shape events
        from .occasions import rebuild_if_idle

        rebuild_if_idle(s)
    return person_dict(p, _person_stats(s).get(p.id))


class MergeIn(BaseModel):
    into_id: int


@router.post("/people/{person_id}/merge")
def merge(person_id: int, body: MergeIn, s: Session = Depends(get_session)):
    _require_idle(s)
    source, target = _get_person(s, person_id), _get_person(s, body.into_id)
    target = merge_people(s, source, target)
    return person_dict(target, _person_stats(s).get(target.id))


@router.get("/people/{person_id}/faces")
def person_faces(person_id: int, s: Session = Depends(get_session)):
    """All faces of a person, least similar to the rest first (likely mistakes on top)."""
    _get_person(s, person_id)
    rows = s.execute(
        select(Face, Media.taken_at, Media.filename)
        .join(Media, Media.id == Face.media_id)
        .where(Face.person_id == person_id, ~Media.missing)
    ).all()
    if not rows:
        return []
    vecs = np.stack([np.frombuffer(f.embedding, dtype=np.float32) for f, _, _ in rows])
    centroid = vecs.mean(axis=0)
    centroid /= np.linalg.norm(centroid) + 1e-8
    sims = vecs @ centroid
    out = [
        {
            "id": f.id,
            "media_id": f.media_id,
            "taken_at": taken,
            "filename": filename,
            "similarity": round(float(sim), 3),
            "assigned_by": f.assigned_by,
            "quality": f.quality,
        }
        for (f, taken, filename), sim in zip(rows, sims)
    ]
    out.sort(key=lambda x: x["similarity"])
    return out


@router.get("/faces/unassigned")
def unassigned_faces(
    offset: int = Query(0, ge=0), limit: int = Query(120, ge=1, le=500), s: Session = Depends(get_session)
):
    q = (
        select(Face, Media.taken_at, Media.filename)
        .join(Media, Media.id == Face.media_id)
        .where(Face.person_id.is_(None), ~Media.missing)
    )
    total = s.scalar(select(func.count()).select_from(q.subquery()))
    rows = s.execute(q.order_by(Face.quality.desc()).offset(offset).limit(limit)).all()
    return {
        "total": total,
        "faces": [
            {"id": f.id, "media_id": f.media_id, "taken_at": t, "filename": fn, "quality": f.quality, "size_px": f.size_px}
            for f, t, fn in rows
        ],
    }


class AssignIn(BaseModel):
    face_ids: list[int]
    person_id: int | None = None  # None (and no new_person_name) = "not this person"
    new_person_name: str | None = None


@router.post("/faces/assign")
def assign_faces(body: AssignIn, s: Session = Depends(get_session)):
    _require_idle(s)
    if not body.face_ids:
        raise HTTPException(400, "No faces selected")
    target = body.person_id
    if body.new_person_name is not None:
        person = Person(name=body.new_person_name.strip() or None)
        s.add(person)
        s.flush()
        target = person.id
    elif target is not None:
        _get_person(s, target)
    reassign_faces(s, body.face_ids, target)
    return {"ok": True, "person_id": target}


@router.post("/people/recluster")
def recluster(s: Session = Depends(get_session)):
    _require_idle(s)
    return recluster_unnamed(s)


@router.get("/faces/{face_id}/crop")
def face_crop(face_id: int):
    p = crop_path(face_id)
    if not p.is_file():
        raise HTTPException(404, "No crop")
    return FileResponse(p, media_type="image/webp", headers={"Cache-Control": "private, max-age=3600"})
