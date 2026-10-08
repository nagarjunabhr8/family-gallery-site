"""Duplicate grouping: exact (SHA-256), near (pHash) and burst (same minute + similar).

Groups are rebuilt from scratch each time (cheap); the user's manual choice is
kept on `Media.pinned_best`, so it survives regrouping. Nothing is deleted.
"""

from collections import defaultdict
from dataclasses import dataclass

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import DupGroup, DupMember, Media, Quality
from .phash import hamming, hash_array

CHUNK = 2048


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def find(self, x: int) -> int:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


@dataclass
class Row:
    id: int
    kind: str
    sha256: str | None
    phash: str | None
    minute: str | None  # "YYYY-MM-DD HH:MM" for reliable capture times only
    pinned: bool
    total: float
    pixels: int


def _near_pairs(ids: list[int], hashes: list[str], threshold: int):
    """All pairs (i, j) with Hamming distance <= threshold, vectorised in chunks."""
    arr = hash_array(hashes)
    n = len(arr)
    for start in range(0, n, CHUNK):
        block = arr[start : start + CHUNK]
        dist = np.bitwise_count(block[:, None] ^ arr[None, :])
        rows, cols = np.nonzero(dist <= threshold)
        for r, c in zip(rows.tolist(), cols.tolist()):
            i = start + r
            if c > i:
                yield ids[i], ids[c]


def compute_groups(rows: list[Row], near_threshold: int, burst_threshold: int, burst_enabled: bool):
    """Return list of (kind, [member ids]) for every group of 2+."""
    uf = UnionFind()
    reasons: dict[tuple[int, int], str] = {}

    def link(a: int, b: int, reason: str) -> None:
        uf.union(a, b)
        reasons.setdefault((min(a, b), max(a, b)), reason)

    by_sha: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        if r.sha256:
            by_sha[r.sha256].append(r.id)
    for ids in by_sha.values():
        for other in ids[1:]:
            link(ids[0], other, "exact")

    photos = [r for r in rows if r.kind == "photo" and r.phash]
    for a, b in _near_pairs([r.id for r in photos], [r.phash for r in photos], near_threshold):
        link(a, b, "near")

    if burst_enabled and burst_threshold > near_threshold:
        by_minute: dict[str, list[Row]] = defaultdict(list)
        for r in photos:
            if r.minute:
                by_minute[r.minute].append(r)
        for bucket in by_minute.values():
            for i, a in enumerate(bucket):
                for b in bucket[i + 1 :]:
                    if hamming(a.phash, b.phash) <= burst_threshold:
                        link(a.id, b.id, "burst")

    members: dict[int, list[int]] = defaultdict(list)
    for r in rows:
        if r.id in uf.parent:
            members[uf.find(r.id)].append(r.id)

    kinds: dict[int, set[str]] = defaultdict(set)
    for (a, _b), reason in reasons.items():
        kinds[uf.find(a)].add(reason)

    out = []
    for root, ids in members.items():
        if len(ids) < 2:
            continue
        k = kinds[root]
        kind = "burst" if "burst" in k else "near" if "near" in k else "exact"
        out.append((kind, sorted(ids)))
    return out


def pick_best(members: list[Row]) -> Row:
    pinned = [m for m in members if m.pinned]
    pool = pinned or members
    return max(pool, key=lambda m: (m.total, m.pixels, -m.id))


def load_rows(s: Session) -> dict[int, Row]:
    q = (
        select(
            Media.id, Media.kind, Media.sha256, Media.phash, Media.taken_at, Media.date_source,
            Media.pinned_best, Media.width, Media.height, Quality.total,
        )
        .outerjoin(Quality, Quality.media_id == Media.id)
        .where(~Media.missing)
    )
    rows = {}
    for mid, kind, sha, ph, taken, src, pinned, w, h, total in s.execute(q):
        reliable_time = src in ("exif", "video_meta")
        rows[mid] = Row(
            id=mid, kind=kind, sha256=sha, phash=ph,
            minute=taken.strftime("%Y-%m-%d %H:%M") if reliable_time else None,
            pinned=bool(pinned), total=total or 0.0, pixels=(w or 0) * (h or 0),
        )
    return rows


def regroup(s: Session, near_threshold: int, burst_threshold: int, burst_enabled: bool) -> dict:
    """Rebuild all duplicate groups. Returns a small summary."""
    rows = load_rows(s)
    groups = compute_groups(list(rows.values()), near_threshold, burst_threshold, burst_enabled)

    s.execute(delete(DupMember))
    s.execute(delete(DupGroup))
    taken = dict(s.execute(select(Media.id, Media.taken_at).where(Media.id.in_(rows))).all()) if rows else {}

    hidden = 0
    for kind, ids in groups:
        members = [rows[i] for i in ids]
        best = pick_best(members)
        group = DupGroup(kind=kind, best_media_id=best.id, size=len(ids), taken_at=taken[best.id])
        s.add(group)
        s.flush()
        for m in members:
            dist = hamming(m.phash, best.phash) if m.phash and best.phash else 0
            s.add(DupMember(media_id=m.id, group_id=group.id, distance=dist))
        hidden += len(ids) - 1
    s.commit()
    return {"groups": len(groups), "hidden": hidden}


def set_best(s: Session, group: DupGroup, media_id: int | None) -> DupGroup:
    """Pin `media_id` as the group's best (or None to return to automatic choice)."""
    member_ids = s.scalars(select(DupMember.media_id).where(DupMember.group_id == group.id)).all()
    if media_id is not None and media_id not in member_ids:
        raise ValueError("Photo is not in this group")
    for m in s.scalars(select(Media).where(Media.id.in_(member_ids))):
        m.pinned_best = m.id == media_id
    s.flush()
    rows = load_rows(s)
    best = pick_best([rows[i] for i in member_ids if i in rows])
    group.best_media_id = best.id
    group.taken_at = s.get(Media, best.id).taken_at
    for dm in s.scalars(select(DupMember).where(DupMember.group_id == group.id)):
        other = rows.get(dm.media_id)
        dm.distance = hamming(other.phash, best.phash) if other and other.phash and best.phash else 0
    s.commit()
    return group
