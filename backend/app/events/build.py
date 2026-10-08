"""Group media into events by time gaps (and GPS jumps), keeping the user's edits.

- Media the user moved by hand, and every member of a locked (user-edited)
  event, stay where they are.
- New media whose time falls inside a locked event's window join it.
- Everything else is regrouped. Clusters smaller than `min_photos` are
  gathered into one "Moments" event per month, unless they fall on a
  festival or family occasion.
- Rebuilt events reuse the id of the old event they overlap most, so links
  and the user's hero picks survive.
"""

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import settings_store
from ..models import Event, EventMedia, Media
from ..occasions.match import OccasionIndex
from .curate import CurateContext


@dataclass
class Item:
    id: int
    taken_at: datetime
    lat: float | None
    lon: float | None

    @property
    def geo(self) -> tuple[float, float] | None:
        if self.lat is None or self.lon is None or (abs(self.lat) < 1e-6 and abs(self.lon) < 1e-6):
            return None
        return self.lat, self.lon


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def split_clusters(items: list[Item], gap_hours: float, gps_km: float) -> list[list[Item]]:
    """Split time-ordered items at long time gaps or big location jumps."""
    clusters: list[list[Item]] = []
    cur: list[Item] = []
    last_geo = None
    for it in sorted(items, key=lambda i: (i.taken_at, i.id)):
        if cur:
            new = it.taken_at - cur[-1].taken_at > timedelta(hours=gap_hours)
            if not new and it.geo and last_geo and haversine_km(last_geo, it.geo) > gps_km:
                new = True
            if new:
                clusters.append(cur)
                cur, last_geo = [], None
        cur.append(it)
        last_geo = it.geo or last_geo
    if cur:
        clusters.append(cur)
    return clusters


def refresh_event(s: Session, e: Event, ctx: CurateContext | None = None) -> bool:
    """Fit an event's time range to its members and refresh the automatic hero.

    Returns False (and deletes the event) when it has no members and isn't custom.
    """
    rows = s.execute(
        select(Media.id, Media.taken_at).join(EventMedia, EventMedia.media_id == Media.id)
        .where(EventMedia.event_id == e.id, ~Media.missing)
    ).all()
    if not rows:
        if e.kind != "custom":
            s.delete(e)
            return False
        e.hero_media_id = None
        return True
    ids = [r[0] for r in rows]
    first, last = min(r[1] for r in rows), max(r[1] for r in rows)
    if e.locked and e.kind == "custom":
        e.start_at, e.end_at = min(e.start_at, first), max(e.end_at, last)
    else:
        e.start_at, e.end_at = first, last
    if not e.hero_by_user or e.hero_media_id not in ids:
        e.hero_by_user = False
        ctx = ctx or CurateContext(s, ids)
        e.hero_media_id, _ = ctx.curate(ids)
    return True


def rebuild_events(s: Session) -> dict:
    cfg = settings_store.get_all(s)
    items = [
        Item(*row)
        for row in s.execute(
            select(Media.id, Media.taken_at, Media.gps_lat, Media.gps_lon)
            .where(~Media.missing).order_by(Media.taken_at, Media.id)
        )
    ]
    live = {it.id for it in items}
    events = {e.id: e for e in s.scalars(select(Event))}
    locked = {eid for eid, e in events.items() if e.locked}
    membership = {mid: (eid, by) for mid, eid, by in s.execute(
        select(EventMedia.media_id, EventMedia.event_id, EventMedia.assigned_by))}

    # 1. keep user placements and members of locked events
    sticky = {mid: eid for mid, (eid, by) in membership.items()
              if mid in live and eid in events and (by == "user" or eid in locked)}

    # 2. new media inside a locked event's time window join it
    windows = sorted((events[eid].start_at, events[eid].end_at, eid) for eid in locked)
    absorbed: dict[int, int] = {}
    free: list[Item] = []
    for it in items:
        if it.id in sticky:
            continue
        home = next((eid for start, end, eid in windows if start <= it.taken_at <= end), None)
        if home is not None:
            absorbed[it.id] = home
        else:
            free.append(it)

    # 3. regroup the rest
    groups: list[tuple[str, list[int]]] = []
    by_month: dict[tuple[int, int], list[int]] = defaultdict(list)
    occasions = OccasionIndex(s)
    for cluster in split_clusters(free, cfg["event_gap_hours"], cfg["event_gps_km"]):
        special_day = occasions.between(cluster[0].taken_at.date(), cluster[-1].taken_at.date())
        if len(cluster) >= cfg["event_min_photos"] or special_day:
            groups.append(("auto", [it.id for it in cluster]))
        else:
            for it in cluster:
                by_month[(it.taken_at.year, it.taken_at.month)].append(it.id)
    groups += [("moments", ids) for _, ids in sorted(by_month.items())]

    # 4. reuse ids of the old unlocked events they overlap most
    old_members: dict[int, set[int]] = defaultdict(set)
    for mid, (eid, _by) in membership.items():
        if eid in events and eid not in locked:
            old_members[eid].add(mid)
    used: set[int] = set()
    placements: list[tuple[Event, list[int]]] = []
    created = 0
    for kind, ids in groups:
        idset = set(ids)
        best, overlap = None, 0
        for eid, olds in old_members.items():
            if eid in used or events[eid].kind != kind:
                continue
            ov = len(idset & olds)
            if ov > overlap:
                best, overlap = eid, ov
        if best is not None:
            used.add(best)
            e = events[best]
        else:
            e = Event(kind=kind, start_at=datetime.now(), end_at=datetime.now())
            s.add(e)
            s.flush()
            created += 1
        placements.append((e, ids))

    # 5. rewrite automatic memberships
    keep = set(sticky)
    s.execute(delete(EventMedia).where(EventMedia.media_id.not_in(keep)))
    for mid, eid in absorbed.items():
        s.add(EventMedia(media_id=mid, event_id=eid, assigned_by="auto"))
    for e, ids in placements:
        for mid in ids:
            s.add(EventMedia(media_id=mid, event_id=e.id, assigned_by="auto"))
    s.flush()

    removed = 0
    for eid, e in events.items():
        if eid not in locked and eid not in used and e.kind != "custom":
            s.delete(e)
            removed += 1
    s.flush()

    ctx = CurateContext(s)
    alive = 0
    for e in s.scalars(select(Event)).all():
        alive += refresh_event(s, e, ctx)
    s.commit()
    return {"events": alive, "created": created, "removed": removed, "kept_edited": len(locked)}


def refresh_heroes(s: Session) -> None:
    """Re-pick automatic heroes (after duplicate picks or people changes)."""
    ctx = CurateContext(s)
    for e in s.scalars(select(Event).where(~Event.hero_by_user)).all():
        refresh_event(s, e, ctx)
    s.commit()


def media_ids_of(s: Session, event_id: int) -> list[int]:
    return list(s.scalars(
        select(EventMedia.media_id).join(Media, Media.id == EventMedia.media_id)
        .where(EventMedia.event_id == event_id, ~Media.missing)
    ))
