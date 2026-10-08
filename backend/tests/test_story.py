"""Our Story (stages, chapters), best of year, on this day, music folder and display rotation."""

from datetime import date, datetime

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.events.build import rebuild_events
from app.models import ClipEmbedding, Media, Occasion, Person, Quality, SourceFolder, StoryStage
from app.story.music import list_tracks, nice_title
from app.story.stages import Chapter, add_years, age_range, chapters, suggest_stages

from .conftest import snapshot


def test_add_years_handles_leap_day():
    assert add_years(date(2000, 2, 29), 5) == date(2005, 2, 28)
    assert add_years(date(2000, 2, 29), 4) == date(2004, 2, 29)


def test_age_range_labels():
    b = date(1990, 6, 15)
    assert age_range(b, Chapter(1, "School", "school", date(1995, 6, 15), date(2007, 6, 15))) == "Age 5 – 17"
    assert age_range(b, Chapter(1, "Now", "kids", date(2020, 1, 1), None)) == "From age 29"
    assert age_range(None, Chapter(1, "x", "x", date(2020, 1, 1), None)) is None


def test_suggest_stages(data_dir):
    with SessionLocal() as s:
        me = Person(name="Nagarjuna", birth_date=date(1990, 6, 15))
        kid = Person(name="Aadhya", birth_date=date(2018, 3, 2))
        s.add_all([me, kid, Occasion(kind="anniversary", name="Us", month=5, day=20, year=2015)])
        s.commit()
        made = suggest_stages(s, me, today=date(2026, 1, 1))
        assert [(st.kind, st.start) for st in made] == [
            ("childhood", date(1990, 6, 15)),
            ("school", date(1995, 6, 15)),
            ("college", date(2007, 6, 15)),
            ("career", date(2012, 6, 15)),
            ("marriage", date(2015, 5, 20)),
            ("kids", date(2018, 3, 2)),
        ]
        # user renames one; re-suggesting keeps it and doesn't duplicate its kind
        college = next(st for st in made if st.kind == "college")
        college.name, college.suggested = "Engineering at JNTU", False
        s.commit()
        again = suggest_stages(s, me, today=date(2026, 1, 1))
        assert "college" not in [st.kind for st in again]
        names = sorted(st.name for st in s.query(StoryStage))
        assert "Engineering at JNTU" in names and len(names) == 6

        chs = chapters(s)
        assert chs[0].name == "Early years" and chs[0].end == date(1990, 6, 15)
        assert chs[-1].kind == "kids" and chs[-1].end is None


def test_suggest_needs_birth_date(data_dir):
    with SessionLocal() as s:
        p = Person(name="X")
        s.add(p)
        s.commit()
        with pytest.raises(ValueError):
            suggest_stages(s, p)


def test_music_listing(tmp_path):
    (tmp_path / "Songs" / ".hidden").mkdir(parents=True)
    (tmp_path / "Songs" / "Ilaiyaraaja_-_Melody.mp3").write_bytes(b"x" * 10)
    (tmp_path / "Songs" / "b.m4a").write_bytes(b"y")
    (tmp_path / "Songs" / "cover.jpg").write_bytes(b"z")
    (tmp_path / "Songs" / ".hidden" / "c.mp3").write_bytes(b"z")
    tracks = list_tracks(tmp_path / "Songs")
    assert [t.rel_path for t in tracks] == ["b.m4a", "Ilaiyaraaja_-_Melody.mp3"]
    assert nice_title("Ilaiyaraaja_-_Melody") == "Ilaiyaraaja - Melody"
    assert len({t.id for t in tracks}) == 2


# ---------- API over a small fake library ----------

@pytest.fixture
def client(data_dir, monkeypatch):
    from app.main import app

    rng = np.random.default_rng(3)
    plan = [datetime(2019, 10, 8, 10), datetime(2019, 10, 8, 11), datetime(2019, 10, 8, 12),
            datetime(2022, 10, 9, 9), datetime(2024, 3, 1, 9), datetime(2024, 3, 1, 10), datetime(2024, 3, 1, 11)]
    with SessionLocal() as s:
        folder = SourceFolder(path="X:/fake")
        s.add(folder)
        s.flush()
        for i, when in enumerate(plan):
            m = Media(folder_id=folder.id, rel_path=f"{i}.jpg", filename=f"{i}.jpg", ext=".jpg", kind="photo",
                      size=1, mtime_ns=1, taken_at=when, date_source="exif", date_confidence="high",
                      width=400, height=300, has_thumb=True, phash=f"{rng.integers(0, 2**63):016x}")
            s.add(m)
            s.flush()
            s.add(Quality(media_id=m.id, version=2, media_mtime_ns=1, sharpness_raw=1, sharpness=0.8,
                          exposure=0.8, resolution=0.8, total=60 + i))
            v = rng.normal(size=512).astype(np.float32)
            s.add(ClipEmbedding(media_id=m.id, model="t", vector=(v / np.linalg.norm(v)).tobytes()))
        s.add(Person(name="Me", birth_date=date(1990, 6, 15)))
        s.add(Person(name="Kid", birth_date=date(2021, 4, 2)))
        s.commit()
        rebuild_events(s)
    monkeypatch.setenv("FM_DATA_DIR", str(data_dir))
    with TestClient(app) as c:
        yield c


def test_story_api(client):
    st = client.get("/api/story").json()
    assert st["owner"] is None and st["stages"] == []
    assert [y["year"] for ch in st["chapters"] for y in ch["years"]] == [1990, 2019, 2021, 2022, 2024]

    people = {p["name"]: p["id"] for p in client.get("/api/people").json()["people"]}
    assert client.post("/api/story/suggest", json={"person_id": people["Kid"]}).json()["created"]
    r = client.post("/api/story/suggest", json={"person_id": people["Me"]}).json()
    kinds = [x["kind"] for x in r["created"]]
    assert kinds[:3] == ["childhood", "school", "college"] and kinds[-1] == "kids"

    st = client.get("/api/story").json()
    assert st["owner"]["name"] == "Me"
    names = [ch["name"] for ch in st["chapters"]]
    assert names[0] == "Childhood" and names[-1] == "Our little ones"
    kids = st["chapters"][-1]
    assert kids["age"] == "From age 30"
    assert [m["label"] for y in kids["years"] for m in y["milestones"]] == ["Kid was born"]
    y2019 = next(y for ch in st["chapters"] for y in ch["years"] if y["year"] == 2019)
    assert y2019["photo_count"] == 3 and y2019["cover_media_id"] and y2019["age"] == "Me turns 29"

    stage = st["stages"][0]
    edited = client.put(f"/api/story/stages/{stage['id']}", json={"name": "Little me", "start": stage["start"]}).json()
    assert edited["name"] == "Little me" and not edited["suggested"]
    added = client.post("/api/story/stages", json={"name": "Hyderabad", "start": "2023-01-01"}).json()
    assert client.delete(f"/api/story/stages/{added['id']}").json()["ok"]


def test_best_and_on_this_day(client):
    years = client.get("/api/best").json()
    assert [y["year"] for y in years] == [2024, 2022, 2019] and years[0]["photo_count"] == 3
    best = client.get("/api/best/2019", params={"limit": 2}).json()
    assert best["photo_count"] == 3 and len(best["items"]) == 2

    otd = client.get("/api/onthisday", params={"day": "2026-10-08"}).json()
    assert otd["span"] == "day" and [y["year"] for y in otd["years"]] == [2019]
    assert otd["years"][0]["label"] == "7 years ago" and otd["years"][0]["total"] == 3
    week = client.get("/api/onthisday", params={"day": "2026-10-11"}).json()
    assert week["span"] == "week" and [y["year"] for y in week["years"]] == [2022, 2019]
    assert client.get("/api/onthisday", params={"day": "2026-07-01"}).json()["years"] == []


def test_music_folder_api_is_read_only(client, tmp_path, data_dir):
    music = tmp_path / "music"
    music.mkdir()
    (music / "song.mp3").write_bytes(b"ID3fake")
    before = snapshot(music)
    assert client.put("/api/music/folder", json={"path": "relative"}).status_code == 400
    assert client.put("/api/music/folder", json={"path": str(data_dir)}).status_code == 400
    r = client.put("/api/music/folder", json={"path": f'"{music}"'}).json()
    assert r["exists"] and [t["title"] for t in r["tracks"]] == ["song"]
    tid = r["tracks"][0]["id"]
    resp = client.get(f"/api/music/{tid}")
    assert resp.status_code == 200 and resp.content == b"ID3fake" and resp.headers["content-type"] == "audio/mpeg"
    assert client.get("/api/music/0000000000000000").status_code == 404
    assert snapshot(music) == before
    assert client.put("/api/music/folder", json={"path": None}).json()["folder"] is None


def test_display_rotation(client):
    mid = client.get("/api/media").json()["items"][0]["id"]
    assert client.put(f"/api/media/{mid}/rotation", json={"rotation": 90}).json()["rotation"] == 90
    assert client.put(f"/api/media/{mid}/rotation", json={"rotation": 45}).status_code == 422
    assert client.get(f"/api/media/{mid}").json()["rotation"] == 90
