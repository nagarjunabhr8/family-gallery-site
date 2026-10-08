"""Face clustering into people.

Stable by design: faces already assigned to a person stay there; only
unassigned faces are matched to existing people (by centroid similarity)
or grouped into new unnamed clusters. Names, merges, splits and "not this
person" corrections are therefore never undone by re-running.
"""

import json
from dataclasses import dataclass

import numpy as np
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from ..models import DupMember, Face, Person

MATCH_THRESHOLD = 0.42  # cosine similarity for joining an existing person
LINK_THRESHOLD = 0.50  # stricter, for starting new clusters from unassigned faces
SEED_QUALITY = 0.30  # faces below this can join people but never seed new ones
MIN_MOMENTS = 2  # a new person needs faces from 2+ different photos (not copies of one)


@dataclass
class FaceVec:
    id: int
    vec: np.ndarray
    person_id: int | None
    not_people: set[int]
    quality: float
    moment: str  # duplicate group (or photo) the face comes from


def _load(s: Session) -> list[FaceVec]:
    rows = s.execute(
        select(Face.id, Face.embedding, Face.person_id, Face.not_person_ids, Face.quality, Face.media_id,
               DupMember.group_id)
        .outerjoin(DupMember, DupMember.media_id == Face.media_id)
    )
    return [
        FaceVec(fid, np.frombuffer(emb, dtype=np.float32), pid, set(json.loads(neg or "[]")), q,
                f"g{gid}" if gid else f"m{mid}")
        for fid, emb, pid, neg, q, mid, gid in rows
    ]


def _centroids(faces: list[FaceVec]) -> tuple[list[int], np.ndarray]:
    sums: dict[int, np.ndarray] = {}
    for f in faces:
        if f.person_id is not None:
            sums[f.person_id] = sums.get(f.person_id, 0) + f.vec
    ids = list(sums)
    if not ids:
        return [], np.zeros((0, 512), dtype=np.float32)
    mat = np.stack([sums[i] for i in ids]).astype(np.float32)
    return ids, mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-8)


def _match_to_people(faces: list[FaceVec], threshold: float, named: set[int]) -> dict[int, int]:
    """Assign each unassigned face to its most similar person above threshold.

    Faces the user has corrected ("not this person") only auto-join *named*
    people: unnamed clusters come and go, so they can't honour the correction.
    """
    ids, cents = _centroids(faces)
    loose = [f for f in faces if f.person_id is None]
    if not ids or not loose:
        return {}
    sims = np.stack([f.vec for f in loose]) @ cents.T
    out = {}
    for row, f in enumerate(loose):
        for col in np.argsort(-sims[row]):
            if sims[row, col] < threshold:
                break
            pid = ids[col]
            if pid in f.not_people or (f.not_people and pid not in named):
                continue
            out[f.id] = pid
            break
    return out


def _new_clusters(faces: list[FaceVec]) -> list[list[FaceVec]]:
    """Leader clustering of good-quality unassigned faces, best faces first.

    Corrected faces never seed or join new clusters (see `_match_to_people`).
    """
    seeds = sorted(
        (f for f in faces if f.person_id is None and f.quality >= SEED_QUALITY and not f.not_people),
        key=lambda f: -f.quality,
    )
    clusters: list[list[FaceVec]] = []
    sums: list[np.ndarray] = []
    for f in seeds:
        best, best_sim = -1, LINK_THRESHOLD
        for i, total in enumerate(sums):
            sim = float(f.vec @ (total / np.linalg.norm(total)))
            if sim >= best_sim:
                best, best_sim = i, sim
        if best >= 0:
            clusters[best].append(f)
            sums[best] = sums[best] + f.vec
        else:
            clusters.append([f])
            sums.append(f.vec.copy())
    # copies of one photo are a single moment: not enough evidence for a new person
    return [c for c in clusters if len({f.moment for f in c}) >= MIN_MOMENTS]


def cluster_faces(s: Session) -> dict:
    faces = _load(s)
    by_id = {f.id: f for f in faces}
    originally_free = {f.id for f in faces if f.person_id is None}
    named = set(s.scalars(select(Person.id).where(Person.name.is_not(None))))
    assigned = 0

    # 1. unassigned faces join people we already know
    for fid, pid in _match_to_people(faces, MATCH_THRESHOLD, named).items():
        by_id[fid].person_id = pid
        assigned += 1

    # 2. the rest form new unnamed clusters
    created = 0
    for cluster in _new_clusters(faces):
        person = Person()
        s.add(person)
        s.flush()
        created += 1
        for f in cluster:
            f.person_id = person.id
            assigned += 1

    # 3. weaker leftovers may now match one of the new clusters
    for fid, pid in _match_to_people(faces, MATCH_THRESHOLD, named).items():
        by_id[fid].person_id = pid
        assigned += 1

    for fid in originally_free:
        pid = by_id[fid].person_id
        if pid is not None:
            s.execute(update(Face).where(Face.id == fid).values(person_id=pid, assigned_by="auto"))
    s.flush()
    cleanup(s)
    s.commit()
    unassigned = sum(1 for f in faces if f.person_id is None)
    return {"assigned": assigned, "new_people": created, "unassigned": unassigned}


def cleanup(s: Session) -> None:
    """Drop empty unnamed clusters and refresh cover faces."""
    counts = dict(s.execute(select(Face.person_id, func.count()).where(Face.person_id.is_not(None)).group_by(Face.person_id)).all())
    for p in s.scalars(select(Person)):
        if not counts.get(p.id) and not p.name and not p.birth_date:
            s.delete(p)
            continue
        cover_ok = p.cover_face_id and s.scalar(
            select(func.count()).where(Face.id == p.cover_face_id, Face.person_id == p.id)
        )
        if not cover_ok:
            p.cover_face_id = s.scalar(
                select(Face.id).where(Face.person_id == p.id).order_by(Face.quality.desc()).limit(1)
            )


def recluster_unnamed(s: Session) -> dict:
    """Dissolve unnamed clusters' automatic assignments and cluster again (keeps all user work)."""
    unnamed = s.scalars(select(Person.id).where(Person.name.is_(None), ~Person.hidden)).all()
    if unnamed:
        s.query(Face).filter(Face.person_id.in_(unnamed), Face.assigned_by == "auto").update(
            {Face.person_id: None}, synchronize_session=False
        )
        s.flush()
        cleanup(s)
    return cluster_faces(s)


def merge_people(s: Session, source: Person, target: Person) -> Person:
    """Move all of source's faces to target; carry over name/birth date if target lacks them."""
    if source.id == target.id:
        return target
    s.query(Face).filter(Face.person_id == source.id).update({Face.person_id: target.id}, synchronize_session=False)
    target.name = target.name or source.name
    target.birth_date = target.birth_date or source.birth_date
    # faces that said "not source" now mean "not target"
    for f in s.scalars(select(Face).where(Face.not_person_ids != "[]")):
        neg = set(json.loads(f.not_person_ids))
        if source.id in neg:
            f.not_person_ids = json.dumps(sorted((neg - {source.id}) | {target.id}))
    s.execute(delete(Person).where(Person.id == source.id))
    s.flush()
    cleanup(s)
    s.commit()
    return target


def reassign_faces(s: Session, face_ids: list[int], person_id: int | None) -> None:
    """User correction. person_id=None means 'not this person' (remembered)."""
    for f in s.scalars(select(Face).where(Face.id.in_(face_ids))):
        if person_id is None:
            if f.person_id is not None:
                neg = set(json.loads(f.not_person_ids or "[]")) | {f.person_id}
                f.not_person_ids = json.dumps(sorted(neg))
            f.person_id = None
            f.assigned_by = "auto"  # free to be matched to someone else
        else:
            f.person_id = person_id
            f.assigned_by = "user"
            neg = set(json.loads(f.not_person_ids or "[]")) - {person_id}
            f.not_person_ids = json.dumps(sorted(neg))
    s.flush()
    cleanup(s)
    s.commit()
