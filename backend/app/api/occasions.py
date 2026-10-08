import calendar
from datetime import date, datetime, time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..events.build import rebuild_events
from ..models import Event, FestivalDate, Occasion, Person, ScanJob
from ..occasions.festivals import FESTIVALS, RANGE_NOTE, reset_festival
from ..occasions.match import on_year
from ..scanner.jobs import ACTIVE

router = APIRouter(prefix="/api", tags=["occasions"])


def rebuild_if_idle(s: Session) -> None:
    """Occasions decide which small clusters become events; regroup unless a job will do it."""
    if not s.scalars(select(ScanJob).where(ScanJob.status.in_(ACTIVE))).first():
        rebuild_events(s)


def occasion_dict(o: Occasion, person_name: str | None = None) -> dict:
    return {
        "id": o.id, "kind": o.kind, "name": o.name, "month": o.month, "day": o.day,
        "year": o.year, "person_id": o.person_id, "person_name": person_name, "source": "occasion",
    }


@router.get("/occasions")
def list_occasions(s: Session = Depends(get_session)):
    names = dict(s.execute(select(Person.id, Person.name)).all())
    items = [occasion_dict(o, names.get(o.person_id)) for o in s.scalars(select(Occasion))]
    linked = {o["person_id"] for o in items if o["kind"] == "birthday" and o["person_id"]}
    # birthdays that come from People pages (read-only here)
    for p in s.scalars(select(Person).where(Person.birth_date.is_not(None), Person.name.is_not(None), ~Person.hidden)):
        if p.id not in linked:
            items.append({
                "id": None, "kind": "birthday", "name": p.name, "month": p.birth_date.month,
                "day": p.birth_date.day, "year": p.birth_date.year, "person_id": p.id,
                "person_name": p.name, "source": "person",
            })
    items.sort(key=lambda o: (o["month"], o["day"], o["name"]))
    return items


class OccasionIn(BaseModel):
    kind: Literal["birthday", "anniversary", "other"]
    name: str = Field(min_length=1, max_length=120)
    month: int = Field(ge=1, le=12)
    day: int = Field(ge=1, le=31)
    year: int | None = Field(None, ge=1900, le=2100)
    person_id: int | None = None

    @model_validator(mode="after")
    def valid_day(self):
        if self.day > calendar.monthrange(self.year or 2000, self.month)[1]:  # 2000 is a leap year
            raise ValueError("That day doesn't exist in that month")
        return self


@router.post("/occasions", status_code=201)
def add_occasion(body: OccasionIn, s: Session = Depends(get_session)):
    if body.person_id is not None and s.get(Person, body.person_id) is None:
        raise HTTPException(400, "Person not found")
    o = Occasion(**body.model_dump())
    o.name = o.name.strip()
    s.add(o)
    s.commit()
    rebuild_if_idle(s)
    return occasion_dict(o)


@router.put("/occasions/{occasion_id}")
def edit_occasion(occasion_id: int, body: OccasionIn, s: Session = Depends(get_session)):
    o = s.get(Occasion, occasion_id)
    if o is None:
        raise HTTPException(404, "Occasion not found")
    for k, v in body.model_dump().items():
        setattr(o, k, v)
    o.name = o.name.strip()
    s.commit()
    rebuild_if_idle(s)
    return occasion_dict(o)


@router.delete("/occasions/{occasion_id}")
def delete_occasion(occasion_id: int, s: Session = Depends(get_session)):
    o = s.get(Occasion, occasion_id)
    if o is None:
        raise HTTPException(404, "Occasion not found")
    s.delete(o)
    s.commit()
    rebuild_if_idle(s)
    return {"ok": True}


def _events_on(s: Session, start: date, end: date) -> list[dict]:
    from .events import Presenter

    events = s.scalars(
        select(Event).where(
            Event.start_at <= datetime.combine(end, time.max),
            Event.end_at >= datetime.combine(start, time.min),
            Event.kind != "moments",
        ).order_by(Event.start_at)
    ).all()
    if not events:
        return []
    p = Presenter(s, [e.id for e in events])
    keys = ("id", "title", "kind", "date_text", "hero_media_id", "photo_count")
    return [{k: d[k] for k in keys} for d in map(p.summary, events)]


def festival_dict(s: Session, f: FestivalDate) -> dict:
    return {
        "id": f.id, "festival": f.festival, "name": FESTIVALS.get(f.festival, f.festival),
        "note": RANGE_NOTE.get(f.festival), "year": f.year, "date": f.date, "start": f.start, "end": f.end,
        "user_edited": f.user_edited, "events": _events_on(s, f.start, f.end),
    }


@router.get("/festivals")
def list_festivals(year: int, s: Session = Depends(get_session)):
    rows = s.scalars(select(FestivalDate).where(FestivalDate.year == year).order_by(FestivalDate.date)).all()
    years = sorted(set(s.scalars(select(FestivalDate.year))))
    return {"year": year, "years": years, "festivals": [festival_dict(s, f) for f in rows]}


class FestivalPatch(BaseModel):
    date: date
    start: date | None = None
    end: date | None = None


@router.patch("/festivals/{festival_id}")
def edit_festival(festival_id: int, body: FestivalPatch, s: Session = Depends(get_session)):
    f = s.get(FestivalDate, festival_id)
    if f is None:
        raise HTTPException(404, "Festival date not found")
    # keep the same shape around the main day (e.g. Bhogi..Kanuma) unless given
    before, after = f.date - f.start, f.end - f.date
    f.date = body.date
    f.start = body.start or body.date - before
    f.end = body.end or body.date + after
    if not (f.start <= f.date <= f.end):
        raise HTTPException(400, "The main day must be within the start and end dates")
    f.user_edited = True
    s.commit()
    rebuild_if_idle(s)
    return festival_dict(s, f)


@router.post("/festivals/{festival_id}/reset")
def reset(festival_id: int, s: Session = Depends(get_session)):
    f = s.get(FestivalDate, festival_id)
    if f is None:
        raise HTTPException(404, "Festival date not found")
    reset_festival(s, f)
    rebuild_if_idle(s)
    return festival_dict(s, f)


@router.get("/occasions/{kind}/{key}/years")
def occasion_years(kind: str, key: str, s: Session = Depends(get_session)):
    """For an occasion, the events in each year it happened (e.g. every Diwali)."""
    out = []
    if kind == "festival":
        for f in s.scalars(select(FestivalDate).where(FestivalDate.festival == key).order_by(FestivalDate.year)):
            ev = _events_on(s, f.start, f.end)
            if ev:
                out.append({"year": f.year, "date": f.date, "events": ev})
        return out
    o = s.get(Occasion, int(key)) if kind == "occasion" else None
    p = s.get(Person, int(key)) if kind == "person" else None
    if o is None and (p is None or p.birth_date is None):
        raise HTTPException(404, "Occasion not found")
    month, day = (o.month, o.day) if o else (p.birth_date.month, p.birth_date.day)
    first = (o.year if o else p.birth_date.year) or 1900
    years = sorted({e.start_at.year for e in s.scalars(select(Event))} | {e.end_at.year for e in s.scalars(select(Event))})
    for y in years:
        if y < first:
            continue
        d = on_year(month, day, y)
        ev = _events_on(s, d, d)
        if ev:
            out.append({"year": y, "date": d, "events": ev})
    return out
