import time

import pytest
from fastapi.testclient import TestClient

from app.main import app

from .conftest import snapshot


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FM_DATA_DIR", str(tmp_path / "data"))
    with TestClient(app) as c:
        yield c


def _wait_for_scan(client, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = client.get("/api/scan/status").json()
        if status["active"] is None and status["last"]:
            return status["last"]
        time.sleep(0.2)
    raise AssertionError("scan did not finish")


def test_add_folder_scan_and_browse(client, sample_folder):
    before = snapshot(sample_folder)

    r = client.post("/api/folders", json={"path": f'"{sample_folder}"'})  # quoted, like "Copy as path"
    assert r.status_code == 201, r.text
    folder_id = r.json()["id"]

    assert client.post("/api/folders", json={"path": str(sample_folder / "2022")}).status_code == 409
    assert client.post("/api/folders", json={"path": "relative\\path"}).status_code == 400
    assert client.post("/api/folders", json={"path": str(sample_folder / "nope")}).status_code == 400

    assert client.post("/api/scan", json={}).status_code == 202
    last = _wait_for_scan(client)  # scan, then the chained analysis job
    assert last["kind"] == "analyze" and last["status"] == "done", last
    assert last["updated"] == 6  # 7 photos, minus broken.jpg

    page = client.get("/api/media", params={"limit": 3}).json()
    assert page["total"] == 8 and len(page["items"]) == 3
    dates = [i["taken_at"] for i in client.get("/api/media").json()["items"]]
    assert dates == sorted(dates, reverse=True)

    photo = next(i for i in page["items"] if i["has_thumb"])
    assert client.get(f"/api/media/{photo['id']}/thumb").headers["content-type"] == "image/webp"
    assert client.get(f"/api/media/{photo['id']}/original").status_code == 200

    stats = client.get("/api/stats").json()
    assert stats["photos"] == 7 and stats["videos"] == 1 and stats["with_errors"] == 1

    detail = client.get(f"/api/media/{photo['id']}").json()
    assert detail["quality"] is None or 0 <= detail["quality"]["total"] <= 100
    assert client.get("/api/groups").json()["total"] == 0  # all sample photos are distinct
    settings = client.put("/api/settings", json={"near_dup_threshold": 12}).json()
    assert settings["settings"]["near_dup_threshold"] == 12

    assert client.get("/api/folders").json()[0]["media_count"] == 8
    assert client.delete(f"/api/folders/{folder_id}").json()["media_forgotten"] == 8
    assert client.get("/api/media").json()["total"] == 0

    assert snapshot(sample_folder) == before
