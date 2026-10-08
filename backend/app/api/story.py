from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from .. import settings_store
from ..db import get_session
from ..events.curate import CurateContext
from ..models import Event, Media, Occasion, Person, Quality, StoryStage
from ..occasions.match import on_year
from ..safety import data_dir, is_inside
from ..story.music import AUDIO_TYPES, list_tracks
from ..story.stages import age_range, chapters, suggest_stages
from .events import Presenter
from .media import hidden_duplicates, summary

router = APIRouter(prefix="/api", tags=["story"])


# ---------- Our Story ----------

def _owner(s: Session) -> Person | None:
    pid = settings_store.get_all(s)["story_person_id"]
    p = s.get(Person, pid) if pid else None
    return p if p is not None and not p.hidden else None


def _milestones(s: Session) -> dict[int, list[dict]]:
    """year -> births and weddings, from People birth dates and anniversaries."""
    out: dict[int, list[dict]] = defaultdict(list)
    for p in s.scalars(select(Person).where(Person.birth_date.is_not(None), Person.name.is_not(None), ~Person.hidden)):
        out[p.birth_date.year].append({"date": p.birth_date, "label": f"{p.name} was born", "kind": "birth", "person_id": p.id})
    for o in s.scalars(select(Occasion).where(Occasion.kind == "anniversary", Occasion.year.is_not(None))):
        out[o.year].append({"date": on_year(o.month, o.day, o.year),
                            "label": f"{o.name}: wedding day", "kind": "wedding", "person_id": None})
    for items in out.values():
        items.sort(key=lambda m: m["date"])
    return out


@router.get("/story")
def story(s: Session = Depends(get_session)):
    events = s.scalars(select(Event).order_by(Event.start_at, Event.id)).all()
    p = Presenter(s, [e.id for e in events])
    owner = _owner(s)
    milestones = _milestones(s)
    chs = chapters(s)

    by_chapter: dict[int, dict[int, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for e in events:
        if not p.members.get(e.id) and e.kind != "custom":
            continue
        d = e.start_at.date()
        idx = next(i for i, ch in enumerate(chs) if ch.contains(d))
        by_chapter[idx][e.start_at.year].append(p.summary(e))

    def year_cover(evs: list[dict]) -> int | None:
        heroes = [p.ctx.media[e["hero_media_id"]] for e in evs if e["hero_media_id"] in p.ctx.media]
        return max(heroes, key=p.ctx.hero_score).id if heroes else None

    out_chapters = []
    for i, ch in enumerate(chs):
        years = by_chapter.get(i, {})
        # milestones also show in years that have no photos
        for y, ms in milestones.items():
            if any(ch.contains(m["date"]) for m in ms) and y not in years:
                years[y] = []
        if not years:
            continue
        out_chapters.append({
            "stage_id": ch.stage_id,
            "name": ch.name,
            "kind": ch.kind,
            "start": ch.start,
            "end": ch.end,
            "age": age_range(owner.birth_date if owner else None, ch),
            "years": [
                {
                    "year": y,
                    "age": _age_in(owner, y),
                    "photo_count": sum(e["photo_count"] for e in evs),
                    "cover_media_id": year_cover(evs),
                    "events": evs,
                    "milestones": [m for m in milestones.get(y, []) if ch.contains(m["date"])],
                }
                for y, evs in sorted(years.items())
            ],
        })

    first, last = s.execute(select(func.min(Media.taken_at), func.max(Media.taken_at)).where(~Media.missing)).one()
    return {
        "owner": {"id": owner.id, "name": owner.name, "birth_date": owner.birth_date} if owner else None,
        "first": first,
        "last": last,
        "photo_count": s.scalar(select(func.count()).where(~Media.missing, Media.kind == "photo")),
        "event_count": sum(len(y["events"]) for ch in out_chapters for y in ch["years"]),
        "stages": [_stage_dict(st) for st in s.scalars(select(StoryStage).order_by(StoryStage.start))],
        "chapters": out_chapters,
    }


def _age_in(owner: Person | None, year: int) -> str | None:
    if owner is None or owner.birth_date is None or year < owner.birth_date.year:
        return None
    n = year - owner.birth_date.year
    return f"{owner.name or 'Age'} turns {n}" if n else f"{owner.name or ''} born".strip()


def _stage_dict(st: StoryStage) -> dict:
    return {"id": st.id, "name": st.name, "start": st.start, "kind": st.kind, "suggested": st.suggested}


class OwnerIn(BaseModel):
    person_id: int | None


@router.put("/story/owner")
def set_owner(body: OwnerIn, s: Session = Depends(get_session)):
    if body.person_id is not None and s.get(Person, body.person_id) is None:
        raise HTTPException(404, "Person not found")
    settings_store.update(s, {"story_person_id": body.person_id})
    return {"ok": True}


@router.post("/story/suggest")
def suggest(body: OwnerIn, s: Session = Depends(get_session)):
    pid = body.person_id or settings_store.get_all(s)["story_person_id"]
    person = s.get(Person, pid) if pid else None
    if person is None:
        raise HTTPException(400, "Choose whose story this is first")
    settings_store.update(s, {"story_person_id": person.id})
    try:
        created = suggest_stages(s, person)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"created": [_stage_dict(st) for st in created]}


class StageIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    start: date


@router.post("/story/stages", status_code=201)
def add_stage(body: StageIn, s: Session = Depends(get_session)):
    st = StoryStage(name=body.name.strip(), start=body.start, kind="custom")
    s.add(st)
    s.commit()
    return _stage_dict(st)


@router.put("/story/stages/{stage_id}")
def edit_stage(stage_id: int, body: StageIn, s: Session = Depends(get_session)):
    st = s.get(StoryStage, stage_id)
    if st is None:
        raise HTTPException(404, "Stage not found")
    st.name, st.start, st.suggested = body.name.strip(), body.start, False
    s.commit()
    return _stage_dict(st)


@router.delete("/story/stages/{stage_id}")
def delete_stage(stage_id: int, s: Session = Depends(get_session)):
    st = s.get(StoryStage, stage_id)
    if st is None:
        raise HTTPException(404, "Stage not found")
    s.delete(st)
    s.commit()
    return {"ok": True}


# ---------- Best of each year ----------

def _year_photo_ids(s: Session, year: int) -> list[int]:
    return list(s.scalars(
        select(Media.id).where(
            ~Media.missing, Media.kind == "photo", Media.has_thumb,
            extract("year", Media.taken_at) == year, Media.id.not_in(hidden_duplicates()),
        )
    ))


@router.get("/best")
def best_years(s: Session = Depends(get_session)):
    year = extract("year", Media.taken_at)
    visible = (~Media.missing, Media.kind == "photo", Media.id.not_in(hidden_duplicates()))
    counts = dict(s.execute(select(year, func.count()).where(*visible).group_by(year)).all())
    best = {}
    for y, mid, total in s.execute(
        select(year, Media.id, Quality.total).join(Quality, Quality.media_id == Media.id).where(*visible)
    ):
        if y not in best or total > best[y][1]:
            best[y] = (mid, total)
    return [
        {"year": int(y), "photo_count": c, "cover_media_id": best.get(y, (None,))[0]}
        for y, c in sorted(counts.items(), reverse=True)
    ]


@router.get("/best/{year}")
def best_of_year(year: int, limit: int = Query(24, ge=1, le=100), s: Session = Depends(get_session)):
    ids = _year_photo_ids(s, year)
    if not ids:
        return {"year": year, "photo_count": 0, "items": []}
    _hero, picks = CurateContext(s, ids).curate(ids, limit=limit)
    rows = {m.id: m for m in s.scalars(select(Media).where(Media.id.in_(picks)))}
    return {"year": year, "photo_count": len(ids), "items": [summary(rows[i]) for i in picks if i in rows]}


# ---------- On this day ----------

@router.get("/onthisday")
def on_this_day(
    day: date | None = None,
    per_year: int = Query(8, ge=1, le=40),
    s: Session = Depends(get_session),
):
    """Photos from this calendar day in earlier years; widens to the same week if the day is empty."""
    day = day or date.today()
    base = select(Media).where(
        ~Media.missing, Media.has_thumb, Media.id.not_in(hidden_duplicates()),
        extract("year", Media.taken_at) < day.year,
    )

    def window(days: int) -> list[Media]:
        rows = s.scalars(base.where(
            extract("month", Media.taken_at).in_({(day + timedelta(d)).month for d in range(-days, days + 1)})
        )).all()
        wanted = set()
        for d in range(-days, days + 1):
            x = day + timedelta(d)
            wanted.add((x.month, x.day))
        return [m for m in rows if (m.taken_at.month, m.taken_at.day) in wanted]

    rows, span = window(0), "day"
    if not rows:
        rows, span = window(3), "week"
    by_year: dict[int, list[Media]] = defaultdict(list)
    for m in rows:
        by_year[m.taken_at.year].append(m)
    out = []
    for y in sorted(by_year, reverse=True):
        ms = by_year[y]
        photos = [m.id for m in ms if m.kind == "photo"]
        ctx = CurateContext(s, [m.id for m in ms])
        _hero, picks = ctx.curate(photos, limit=per_year) if photos else (None, [])
        chosen = picks or [m.id for m in sorted(ms, key=lambda m: m.taken_at)[:per_year]]
        by_id = {m.id: m for m in ms}
        n = day.year - y
        out.append({
            "year": y,
            "years_ago": n,
            "label": "A year ago" if n == 1 else f"{n} years ago",
            "total": len(ms),
            "items": [summary(by_id[i]) for i in chosen],
        })
    return {"date": day, "span": span, "years": out}


# ---------- Music ----------

class MusicFolderIn(BaseModel):
    path: str | None


def _music_folder(s: Session) -> Path | None:
    p = settings_store.get_all(s)["music_folder"]
    return Path(p) if p else None


@router.get("/music")
def music(s: Session = Depends(get_session)):
    folder = _music_folder(s)
    if folder is None:
        return {"folder": None, "exists": False, "tracks": []}
    if not folder.is_dir():
        return {"folder": str(folder), "exists": False, "tracks": []}
    return {"folder": str(folder), "exists": True, "tracks": [t.as_dict() for t in list_tracks(folder)]}


@router.put("/music/folder")
def set_music_folder(body: MusicFolderIn, s: Session = Depends(get_session)):
    if body.path is None or not body.path.strip():
        settings_store.update(s, {"music_folder": None})
        return music(s)
    raw = body.path.strip().strip('"').strip("'")
    folder = Path(raw)
    if not folder.is_absolute():
        raise HTTPException(400, "Please enter a full folder path, like D:\\Music")
    if not folder.is_dir():
        raise HTTPException(400, "That folder doesn't exist")
    folder = folder.resolve()
    if is_inside(folder, data_dir()) or is_inside(data_dir(), folder):
        raise HTTPException(400, "Choose a folder outside the app's data folder")
    settings_store.update(s, {"music_folder": str(folder)})
    return music(s)


@router.get("/music/{track_id}")
def music_file(track_id: str, s: Session = Depends(get_session)):
    """Stream a song (read-only)."""
    folder = _music_folder(s)
    if folder is None or not folder.is_dir():
        raise HTTPException(404, "No music folder")
    track = next((t for t in list_tracks(folder) if t.id == track_id), None)
    if track is None:
        raise HTTPException(404, "Song not found")
    path = folder / track.rel_path
    if not is_inside(path, folder):
        raise HTTPException(400, "Invalid path")
    return FileResponse(path, media_type=AUDIO_TYPES[path.suffix.lower()])


# ---------- display rotation ----------

class RotationIn(BaseModel):
    rotation: Literal[0, 90, 180, 270]


@router.put("/media/{media_id}/rotation")
def set_rotation(media_id: int, body: RotationIn, s: Session = Depends(get_session)):
    """Turn a photo in the app only. The original file is never changed."""
    m = s.get(Media, media_id)
    if m is None:
        raise HTTPException(404, "Not found")
    m.user_rotation = body.rotation
    s.commit()
    return summary(m)
