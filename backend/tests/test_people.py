"""Face clustering, naming, merge/split stability — with synthetic ArcFace-like embeddings."""

import json
from datetime import datetime

import numpy as np
import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Face, Media, Person, SourceFolder
from app.people.cluster import cluster_faces, merge_people, reassign_faces, recluster_unnamed

RNG = np.random.default_rng(42)
IDENTITIES = {name: RNG.normal(size=512) for name in ("amma", "nanna", "baby")}


def _vec(identity: str | None, noise=0.35) -> np.ndarray:
    base = IDENTITIES[identity] if identity else RNG.normal(size=512)
    v = base / np.linalg.norm(base) + RNG.normal(size=512) * noise / np.sqrt(512)
    return (v / np.linalg.norm(v)).astype(np.float32)


@pytest.fixture
def faces(data_dir):
    """10 amma, 6 nanna, 4 baby faces and 3 strangers, each in its own photo."""
    plan = ["amma"] * 10 + ["nanna"] * 6 + ["baby"] * 4 + [None] * 3
    with SessionLocal() as s:
        folder = SourceFolder(path="X:/fake")
        s.add(folder)
        s.flush()
        ids = {}
        for i, who in enumerate(plan):
            m = Media(folder_id=folder.id, rel_path=f"{i}.jpg", filename=f"{i}.jpg", ext=".jpg", kind="photo",
                      size=1, mtime_ns=1, taken_at=datetime(2020, 1, 1 + i), date_source="exif",
                      date_confidence="high")
            s.add(m)
            s.flush()
            f = Face(media_id=m.id, x=0.1, y=0.1, w=0.2, h=0.2, landmarks="[]", det_score=0.9, size_px=150,
                     quality=0.8, embedding=_vec(who).tobytes())
            s.add(f)
            s.flush()
            ids.setdefault(who, []).append(f.id)
        s.commit()
    return ids


def _people(s) -> dict[int, set[int]]:
    out: dict[int, set[int]] = {}
    for fid, pid in s.execute(select(Face.id, Face.person_id).where(Face.person_id.is_not(None))):
        out.setdefault(pid, set()).add(fid)
    return out


def _person_of(s, face_id) -> int | None:
    s.expire_all()  # clustering uses bulk updates
    return s.get(Face, face_id).person_id


def test_clusters_match_identities(faces):
    with SessionLocal() as s:
        result = cluster_faces(s)
        clusters = sorted(_people(s).values(), key=len, reverse=True)
    assert result["new_people"] == 3
    assert clusters == [set(faces["amma"]), set(faces["nanna"]), set(faces["baby"])]
    assert result["unassigned"] == 3  # strangers stay unassigned, not a "person" each


def test_copies_of_one_photo_do_not_make_a_person(faces):
    from app.models import DupGroup, DupMember

    with SessionLocal() as s:
        # the 3 strangers' photos are declared copies of one moment, and all share one face
        stranger_faces = [s.get(Face, fid) for fid in faces[None]]
        same = _vec(None)
        for f in stranger_faces:
            f.embedding = same.tobytes()
        g = DupGroup(kind="exact", best_media_id=stranger_faces[0].media_id, size=3, taken_at=datetime(2020, 1, 1))
        s.add(g)
        s.flush()
        s.add_all(DupMember(media_id=f.media_id, group_id=g.id) for f in stranger_faces)
        s.commit()
        cluster_faces(s)
        assert all(_person_of(s, fid) is None for fid in faces[None])


def test_named_person_is_stable_and_absorbs_new_faces(faces, data_dir):
    with SessionLocal() as s:
        cluster_faces(s)
        amma_id = _person_of(s, faces["amma"][0])
        s.get(Person, amma_id).name = "Amma"
        s.commit()

        # a new photo of amma arrives
        m = s.scalars(select(Media)).first()
        new = Face(media_id=m.id, x=0.5, y=0.5, w=0.1, h=0.1, landmarks="[]", det_score=0.9, size_px=120,
                   quality=0.7, embedding=_vec("amma").tobytes())
        s.add(new)
        s.commit()
        cluster_faces(s)
        assert _person_of(s, new.id) == amma_id
        assert s.get(Person, amma_id).name == "Amma"


def test_not_this_person_is_remembered(faces):
    with SessionLocal() as s:
        cluster_faces(s)
        amma_id = _person_of(s, faces["amma"][0])
        wrong = faces["amma"][3]
        reassign_faces(s, [wrong], None)
        assert _person_of(s, wrong) is None
        assert amma_id in json.loads(s.get(Face, wrong).not_person_ids)

        # survives re-clustering of unnamed clusters...
        recluster_unnamed(s)
        cluster_faces(s)
        new_amma = _person_of(s, faces["amma"][0])
        assert new_amma != amma_id  # ids are never reused
        assert _person_of(s, wrong) is None



def test_not_this_named_person_is_permanent(faces):
    with SessionLocal() as s:
        cluster_faces(s)
        amma_id = _person_of(s, faces["amma"][0])
        s.get(Person, amma_id).name = "Amma"
        s.commit()
        wrong = faces["amma"][5]
        reassign_faces(s, [wrong], None)
        for _ in range(2):
            recluster_unnamed(s)
            cluster_faces(s)
            assert _person_of(s, wrong) is None


def test_corrected_face_can_join_another_named_person(faces):
    with SessionLocal() as s:
        cluster_faces(s)
        nanna_id = _person_of(s, faces["nanna"][0])
        s.get(Person, nanna_id).name = "Nanna"
        s.commit()
        # user wrongly removes a real Nanna face from Nanna, then fixes it by moving it back
        face = faces["nanna"][2]
        reassign_faces(s, [face], None)
        assert _person_of(s, face) is None
        reassign_faces(s, [face], nanna_id)
        assert _person_of(s, face) == nanna_id


def test_user_assignment_survives_recluster(faces):
    with SessionLocal() as s:
        cluster_faces(s)
        nanna_id = _person_of(s, faces["nanna"][0])
        s.get(Person, nanna_id).name = "Nanna"
        stranger = faces[None][0]
        reassign_faces(s, [stranger], nanna_id)  # user says: this blurry one is Nanna too
        recluster_unnamed(s)
        assert _person_of(s, stranger) == nanna_id
        assert s.get(Face, stranger).assigned_by == "user"


def test_merge_people(faces):
    with SessionLocal() as s:
        cluster_faces(s)
        a, b = _person_of(s, faces["amma"][0]), _person_of(s, faces["baby"][0])
        s.get(Person, b).name = "Little one"
        s.commit()
        target = merge_people(s, s.get(Person, b), s.get(Person, a))
        assert target.id == a and target.name == "Little one"
        assert s.get(Person, b) is None
        assert set(faces["amma"] + faces["baby"]) <= _people(s)[a]


def test_new_person_from_selection(faces):
    with SessionLocal() as s:
        cluster_faces(s)
        p = Person(name="Visitor")
        s.add(p)
        s.flush()
        reassign_faces(s, faces[None], p.id)
        assert _people(s)[p.id] == set(faces[None])
        assert s.get(Person, p.id).cover_face_id in faces[None]
