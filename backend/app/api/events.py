import math
from collections import Counter
from datetime import date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import extract, select
from sqlalchemy.orm import Session

from ..db import get_session
from ..events.build import media_ids_of, rebuild_events, refresh_event
from ..events.curate import CurateContext
from ..events.tags import LABELS
from ..models import Event, EventMedia, Media, MediaTag, Person
from ..occasions.match import OccasionIndex, span_days
from .media import summary
from .people import _require_idle

router = APIRouter(prefix="/api", tags=["events"])

TAG_TITLES = {
    "birthday": "Birthday celebration",
    "wedding": "Wedding",
    "temple": "Temple visit",
    "school": "School day",
    "travel": "Trip",
    "beach": "Beach day",
}


def date_text(start: datetime, end: datetime) -> str:
    a, b = start.date(), end.date()
    if a == b:
        return f"{a.day} {a:%b %Y}"
    if (a.year, a.month) == (b.year, b.month):
        return f"{a.day} – {b.day} {a:%b %Y}"
    if a.year == b.year:
        return f"{a.day} {a:%b} – {b.day} {b:%b %Y}"
    return f"{a.day} {a:%b %Y} – {b.day} {b:%b %Y}"


class Presenter:
    """Builds event dicts with titles, occasions, tags and people, sharing loaded data."""

    def __init__(self, s: Session, event_ids: list[int] | None = None) -> None:
        self.s = s
        q = select(EventMedia.event_id, EventMedia.media_id).join(Media, Media.id == EventMedia.media_id).where(~Media.missing)
        if event_ids is not None:
            q = q.where(EventMedia.event_id.in_(event_ids))
        self.members: dict[int, list[int]] = {}
        for eid, mid in s.execute(q):
            self.members.setdefault(eid, []).append(mid)
        all_ids = [m for ids in self.members.values() for m in ids]
        self.ctx = CurateContext(s, all_ids)
        self.occasions = OccasionIndex(s)
        self.tags: dict[int, list[str]] = {}
        for mid, tag in s.execute(select(MediaTag.media_id, MediaTag.tag).where(MediaTag.media_id.in_(all_ids))):
            self.tags.setdefault(mid, []).append(tag)
        self.names = dict(s.execute(select(Person.id, Person.name).where(Person.name.is_not(None))).all())

    def event_tags(self, ids: list[int]) -> list[str]:
        photos = [i for i in ids if i in self.ctx.media and self.ctx.media[i].kind == "photo"
                  and not self.ctx.media[i].hidden_copy]
        if not photos:
            return []
        counts = Counter(t for i in photos for t in self.tags.get(i, []))
        need = max(1, math.ceil(0.3 * len(photos)))
        return [t for t, c in counts.most_common() if c >= need]

    def summary(self, e: Event) -> dict:
        ids = self.members.get(e.id, [])
        # a month of "Moments" only spans occasions; photos taken on one get their own event
        hits = [] if e.kind == "moments" else self.occasions.between(e.start_at.date(), e.end_at.date())
        tags = self.event_tags(ids)
        span = span_days(e.start_at.date(), e.end_at.date())
        if e.title:
            title = e.title
        elif e.kind == "moments":
            title = f"Moments · {e.start_at:%B %Y}"
        elif hits and span <= 4:
            title = hits[0].name
        elif tags:
            title = f"{TAG_TITLES[tags[0]]} · {date_text(e.start_at, e.end_at)}"
        else:
            title = date_text(e.start_at, e.end_at)
        people = sorted(self.ctx.people_counts(ids).items(), key=lambda kv: -kv[1])
        kinds = Counter(self.ctx.media[i].kind for i in ids if i in self.ctx.media)
        return {
            "id": e.id,
            "kind": e.kind,
            "title": title,
            "custom_title": e.title,
            "description": e.description,
            "date_text": date_text(e.start_at, e.end_at),
            "start_at": e.start_at,
            "end_at": e.end_at,
            "days": span,
            "locked": e.locked,
            "hero_media_id": e.hero_media_id,
            "hero_by_user": e.hero_by_user,
            "photo_count": kinds.get("photo", 0),
            "video_count": kinds.get("video", 0),
            "occasions": [h.as_dict() for h in hits],
            "tags": [{"tag": t, "label": LABELS[t]} for t in tags],
            "people": [{"id": pid, "name": self.names.get(pid), "count": c} for pid, c in people[:6]],
        }


def _get_event(s: Session, event_id: int) -> Event:
    e = s.get(Event, event_id)
    if not e:
        raise HTTPException(404, "Event not found")
    return e


def _detail(s: Session, e: Event) -> dict:
    p = Presenter(s, [e.id])
    ids = p.members.get(e.id, [])
    _hero, curated = p.ctx.curate(ids)
    rows = s.scalars(select(Media).where(Media.id.in_(ids)).order_by(Media.taken_at, Media.id)).all()
    by_id = {m.id: m for m in rows}
    return {
        **p.summary(e),
        "curated": [summary(by_id[i]) for i in curated if i in by_id],
        "media": [
            {**summary(m), "hidden_copy": p.ctx.media[m.id].hidden_copy, "tags": p.tags.get(m.id, [])}
            for m in rows
        ],
    }


@router.get("/events")
def list_events(
    year: int | None = None,
    include_moments: bool = True,
    order: str = Query("desc", pattern="^(asc|desc)$"),
    s: Session = Depends(get_session),
):
    q = select(Event)
    if year:
        q = q.where(extract("year", Event.start_at) == year)
    if not include_moments:
        q = q.where(Event.kind != "moments")
    q = q.order_by(Event.start_at.asc() if order == "asc" else Event.start_at.desc(), Event.id)
    events = s.scalars(q).all()
    p = Presenter(s, [e.id for e in events])
    years = sorted({e.start_at.year for e in s.scalars(select(Event))}, reverse=True)
    return {"years": years, "events": [p.summary(e) for e in events if p.members.get(e.id) or e.kind == "custom"]}


@router.get("/events/{event_id}")
def get_event(event_id: int, s: Session = Depends(get_session)):
    return _detail(s, _get_event(s, event_id))


class EventPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    hero_media_id: int | None = None  # null = let the app choose


@router.patch("/events/{event_id}")
def update_event(event_id: int, body: EventPatch, s: Session = Depends(get_session)):
    e = _get_event(s, event_id)
    fields = body.model_fields_set
    if "title" in fields:
        e.title = (body.title or "").strip() or None
        e.locked = True
    if "description" in fields:
        e.description = (body.description or "").strip() or None
        e.locked = True
    if "hero_media_id" in fields:
        if body.hero_media_id is None:
            e.hero_by_user = False
        else:
            if body.hero_media_id not in media_ids_of(s, e.id):
                raise HTTPException(400, "That photo is not in this event")
            e.hero_media_id, e.hero_by_user = body.hero_media_id, True
    refresh_event(s, e)
    s.commit()
    return _detail(s, e)


class NewEventIn(BaseModel):
    title: str = Field(min_length=1)
    start: date
    end: date
    description: str | None = None


@router.post("/events", status_code=201)
def create_event(body: NewEventIn, s: Session = Depends(get_session)):
    """A custom event: claims every photo in its date range that you haven't placed by hand."""
    _require_idle(s)
    if body.end < body.start:
        raise HTTPException(400, "End date is before start date")
    e = Event(
        kind="custom", locked=True, title=body.title.strip(), description=body.description,
        start_at=datetime.combine(body.start, time.min), end_at=datetime.combine(body.end, time.max),
    )
    s.add(e)
    s.flush()
    claimed = s.scalars(
        select(EventMedia).join(Media, Media.id == EventMedia.media_id)
        .where(Media.taken_at >= e.start_at, Media.taken_at <= e.end_at, EventMedia.assigned_by == "auto")
    ).all()
    touched = {em.event_id for em in claimed}
    for em in claimed:
        em.event_id = e.id
    s.flush()
    for eid in touched:
        other = s.get(Event, eid)
        if other is not None:
            refresh_event(s, other)
    refresh_event(s, e)
    s.commit()
    return _detail(s, e)


class MergeIn(BaseModel):
    event_ids: list[int] = Field(min_length=2)


@router.post("/events/merge")
def merge_events(body: MergeIn, s: Session = Depends(get_session)):
    """Merge into the earliest event; its title (or the first custom title) is kept."""
    _require_idle(s)
    evs = sorted((_get_event(s, i) for i in set(body.event_ids)), key=lambda e: e.start_at)
    target, rest = evs[0], evs[1:]
    target.title = target.title or next((e.title for e in rest if e.title), None)
    target.description = target.description or next((e.description for e in rest if e.description), None)
    if target.kind == "moments":
        target.kind = "auto"
    target.locked = True
    for e in rest:
        s.query(EventMedia).filter(EventMedia.event_id == e.id).update({EventMedia.event_id: target.id})
        s.delete(e)
    s.flush()
    refresh_event(s, target)
    s.commit()
    return _detail(s, target)


class SplitIn(BaseModel):
    media_id: int  # this photo and everything after it go to a new event


@router.post("/events/{event_id}/split")
def split_event(event_id: int, body: SplitIn, s: Session = Depends(get_session)):
    _require_idle(s)
    e = _get_event(s, event_id)
    ids = media_ids_of(s, e.id)
    pivot = s.get(Media, body.media_id)
    if pivot is None or pivot.id not in ids:
        raise HTTPException(400, "That photo is not in this event")
    rows = s.execute(select(Media.id, Media.taken_at).where(Media.id.in_(ids))).all()
    later = [mid for mid, t in rows if (t, mid) >= (pivot.taken_at, pivot.id)]
    if len(later) == len(ids):
        raise HTTPException(400, "Choose a photo after the first one to split there")
    new = Event(kind="auto", locked=True, start_at=pivot.taken_at, end_at=pivot.taken_at)
    s.add(new)
    s.flush()
    s.query(EventMedia).filter(EventMedia.media_id.in_(later)).update(
        {EventMedia.event_id: new.id}, synchronize_session=False
    )
    e.locked = True
    if e.kind == "moments":
        e.kind = "auto"
    if e.kind == "custom":  # the custom window shrinks to what's left
        e.end_at = max(t for mid, t in rows if mid not in later)
    s.flush()
    refresh_event(s, e)
    refresh_event(s, new)
    s.commit()
    return {"event": _detail(s, e), "new_event_id": new.id}


class MoveIn(BaseModel):
    media_ids: list[int] = Field(min_length=1)
    event_id: int | None = None  # None = into a new event
    new_title: str | None = None


@router.post("/events/move")
def move_media(body: MoveIn, s: Session = Depends(get_session)):
    _require_idle(s)
    if body.event_id is not None:
        target = _get_event(s, body.event_id)
    else:
        t = s.scalars(select(Media.taken_at).where(Media.id.in_(body.media_ids))).all()
        if not t:
            raise HTTPException(400, "No such photos")
        target = Event(kind="auto", locked=True, title=(body.new_title or "").strip() or None,
                       start_at=min(t), end_at=max(t))
        s.add(target)
        s.flush()
    sources = set()
    for mid in body.media_ids:
        em = s.get(EventMedia, mid)
        if em is None:
            if s.get(Media, mid) is None:
                continue
            em = EventMedia(media_id=mid, event_id=target.id)
            s.add(em)
        else:
            sources.add(em.event_id)
        em.event_id, em.assigned_by = target.id, "user"
    s.flush()
    for eid in sources - {target.id}:
        e = s.get(Event, eid)
        if e is not None:
            refresh_event(s, e)
    refresh_event(s, target)
    s.commit()
    return {"event_id": target.id}


@router.delete("/events/{event_id}")
def dissolve_event(event_id: int, s: Session = Depends(get_session)):
    """Undo your edits for this event: its photos go back to automatic grouping."""
    _require_idle(s)
    e = _get_event(s, event_id)
    s.delete(e)
    s.commit()
    return rebuild_events(s)


@router.post("/events/rebuild")
def rebuild(s: Session = Depends(get_session)):
    _require_idle(s)
    return rebuild_events(s)
