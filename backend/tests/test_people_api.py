"""People API flows (naming, birth dates/ages, corrections, merge, hide) with synthetic faces."""

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.people.cluster import cluster_faces

from .test_people import faces  # noqa: F401  (fixture: 10 amma, 6 nanna, 4 baby, 3 strangers)


@pytest.fixture
def client(faces, data_dir, monkeypatch):  # noqa: F811
    from app.main import app

    with SessionLocal() as s:
        cluster_faces(s)
    monkeypatch.setenv("FM_DATA_DIR", str(data_dir))
    with TestClient(app) as c:
        yield c


def _by_size(client):
    return sorted(client.get("/api/people").json()["people"], key=lambda p: -p["face_count"])


def test_name_birth_date_and_ages(client):
    amma, nanna, baby = _by_size(client)[:3]
    assert (amma["face_count"], nanna["face_count"], baby["face_count"]) == (10, 6, 4)

    r = client.patch(f"/api/people/{baby['id']}", json={"name": "  Aadhya  ", "birth_date": "2019-12-15"}).json()
    assert r["name"] == "Aadhya" and r["birth_date"] == "2019-12-15"
    photos = client.get(f"/api/people/{baby['id']}").json()["photos"]
    assert [p["taken_at"][:10] for p in photos] == sorted(p["taken_at"][:10] for p in photos)  # oldest first
    assert all(p["age"] for p in photos)

    assert client.patch(f"/api/people/{baby['id']}", json={"name": ""}).json()["name"] is None
    assert client.get("/api/people/99999").status_code == 404


def test_not_this_person_move_and_new_person(client):
    amma, nanna, _baby = _by_size(client)[:3]
    faces = client.get(f"/api/people/{amma['id']}/faces").json()
    assert len(faces) == 10
    sims = [f["similarity"] for f in faces]
    assert sims == sorted(sims)  # least certain first

    client.post("/api/faces/assign", json={"face_ids": [faces[0]["id"]], "person_id": None})
    assert len(client.get(f"/api/people/{amma['id']}/faces").json()) == 9
    assert client.get("/api/faces/unassigned").json()["total"] >= 1

    client.post("/api/faces/assign", json={"face_ids": [faces[1]["id"]], "person_id": nanna["id"]})
    assert len(client.get(f"/api/people/{nanna['id']}/faces").json()) == 7

    r = client.post("/api/faces/assign", json={"face_ids": [faces[2]["id"]], "new_person_name": "Ammamma"}).json()
    newp = client.get(f"/api/people/{r['person_id']}").json()
    assert newp["name"] == "Ammamma" and newp["face_count"] == 1

    assert client.post("/api/faces/assign", json={"face_ids": []}).status_code == 400


def test_merge_hide_and_recluster(client):
    amma, nanna, baby = _by_size(client)[:3]
    client.patch(f"/api/people/{nanna['id']}", json={"name": "Nanna"})
    merged = client.post(f"/api/people/{baby['id']}/merge", json={"into_id": nanna["id"]}).json()
    assert merged["id"] == nanna["id"] and merged["face_count"] == 10 and merged["name"] == "Nanna"
    assert client.get(f"/api/people/{baby['id']}").status_code == 404

    client.patch(f"/api/people/{amma['id']}", json={"hidden": True})
    ids = [p["id"] for p in client.get("/api/people").json()["people"]]
    assert amma["id"] not in ids
    assert amma["id"] in [p["id"] for p in client.get("/api/people", params={"include_hidden": True}).json()["people"]]

    r = client.post("/api/people/recluster").json()
    assert set(r) == {"assigned", "new_people", "unassigned"}
    assert client.get(f"/api/people/{nanna['id']}").json()["name"] == "Nanna"  # named people survive


def test_face_crop_missing_is_404(client):
    assert client.get("/api/faces/123456/crop").status_code == 404
