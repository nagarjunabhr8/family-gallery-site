"""Pick an event's hero photo and a small set of its best, non-repetitive shots."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..analysis.phash import hamming
from ..models import ClipEmbedding, DupGroup, DupMember, Face, Media, Person, Quality

CURATED_MAX = 12
SAME_SCENE_COS = 0.93  # CLIP similarity: practically the same picture
BURST_COS = 0.88  # ...or quite similar and taken within BURST_SECONDS
BURST_SECONDS = 90
SAME_PHASH = 10


@dataclass
class MediaInfo:
    id: int
    kind: str
    taken_at: datetime
    landscape: bool
    has_thumb: bool
    quality: float | None = None
    aesthetic: float | None = None
    phash: str | None = None
    vec: np.ndarray | None = None
    people: set[int] = field(default_factory=set)
    hidden_copy: bool = False  # a non-best member of a duplicate group


class CurateContext:
    """Everything curation needs, loaded once for a set of media."""

    def __init__(self, s: Session, media_ids: list[int] | None = None) -> None:
        def scoped(q, col):
            return q if media_ids is None else q.where(col.in_(media_ids))

        self.media: dict[int, MediaInfo] = {}
        for m in s.scalars(scoped(select(Media).where(~Media.missing), Media.id)):
            self.media[m.id] = MediaInfo(
                id=m.id,
                kind=m.kind,
                taken_at=m.taken_at,
                landscape=(m.width or 0) >= (m.height or 0),
                has_thumb=m.has_thumb,
                phash=m.phash,
            )
        for mid, total, aes in s.execute(scoped(select(Quality.media_id, Quality.total, Quality.aesthetic), Quality.media_id)):
            if mid in self.media:
                self.media[mid].quality, self.media[mid].aesthetic = total, aes
        for mid, vec in s.execute(scoped(select(ClipEmbedding.media_id, ClipEmbedding.vector), ClipEmbedding.media_id)):
            if mid in self.media:
                self.media[mid].vec = np.frombuffer(vec, dtype=np.float32)
        visible_people = (
            select(Face.media_id, Face.person_id)
            .join(Person, Person.id == Face.person_id)
            .where(~Person.hidden)
        )
        for mid, pid in s.execute(scoped(visible_people, Face.media_id)):
            if mid in self.media:
                self.media[mid].people.add(pid)
        hidden = (
            select(DupMember.media_id)
            .join(DupGroup, DupGroup.id == DupMember.group_id)
            .where(DupGroup.best_media_id != DupMember.media_id)
        )
        for (mid,) in s.execute(scoped(hidden, DupMember.media_id)):
            if mid in self.media:
                self.media[mid].hidden_copy = True

    # ---------- scoring ----------

    @staticmethod
    def score(m: MediaInfo) -> float:
        base = m.quality if m.quality is not None else 50.0
        return base + 4 * min(len(m.people), 3)

    @classmethod
    def hero_score(cls, m: MediaInfo) -> float:
        return cls.score(m) + (6 if m.landscape else 0) + 10 * (m.aesthetic or 0)

    @staticmethod
    def too_similar(a: MediaInfo, b: MediaInfo) -> bool:
        if a.phash and b.phash and hamming(a.phash, b.phash) <= SAME_PHASH:
            return True
        if a.vec is not None and b.vec is not None:
            cos = float(a.vec @ b.vec)
            if cos >= SAME_SCENE_COS:
                return True
            if cos >= BURST_COS and abs((a.taken_at - b.taken_at).total_seconds()) <= BURST_SECONDS:
                return True
        return False

    # ---------- selection ----------

    def curate(self, member_ids: list[int], limit: int = CURATED_MAX) -> tuple[int | None, list[int]]:
        """(hero id, curated ids in time order). Curated photos are all distinct-looking."""
        photos = [
            self.media[i] for i in member_ids
            if i in self.media and self.media[i].kind == "photo" and self.media[i].has_thumb
            and not self.media[i].hidden_copy
        ]
        if not photos:
            videos = sorted((self.media[i] for i in member_ids if i in self.media and self.media[i].has_thumb),
                            key=lambda m: m.taken_at)
            return (videos[0].id if videos else None), []
        picks: list[MediaInfo] = []
        for m in sorted(photos, key=lambda m: (-self.score(m), m.taken_at)):
            if len(picks) >= limit:
                break
            if not any(self.too_similar(m, p) for p in picks):
                picks.append(m)
        hero = max(picks, key=self.hero_score)
        return hero.id, [p.id for p in sorted(picks, key=lambda m: m.taken_at)]

    def people_counts(self, member_ids: list[int]) -> dict[int, int]:
        counts: dict[int, int] = defaultdict(int)
        for i in member_ids:
            if i in self.media and not self.media[i].hidden_copy:
                for pid in self.media[i].people:
                    counts[pid] += 1
        return counts
