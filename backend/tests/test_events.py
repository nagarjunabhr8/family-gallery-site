"""Events: time/GPS grouping, keeping user edits, occasions, festivals and curation."""

import json
from datetime import date, datetime, timedelta

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.events.build import Item, haversine_km, rebuild_events, split_clusters
from app.events.curate import CurateContext
from app.events.tags import tag_probabilities
from app.models import ClipEmbedding, Event, EventMedia, Media, Person, Quality, SourceFolder
from app.occasions.festivals import FESTIVALS, builtin_table, seed_festivals
from app.occasions.match import OccasionIndex, on_year, ordinal

HYD = (17.385, 78.4867)
GOA = (15.2993, 74.1240)


def _items(*spec):
    """spec: (datetime, geo or None) tuples."""
    return [Item(i, t, *(g or (None, None))) for i, (t, g) in enumerate(spec)]


# ---------- pure grouping ----------

def test_split_by_time_gap():
    t = datetime(2024, 5, 1, 9)
    items = _items((t, None), (t + timedelta(hours=2), None), (t + timedelta(hours=10), None))
    assert [len(c) for c in split_clusters(items, gap_hours=6, gps_km=30)] == [2, 1]
    assert [len(c) for c in split_clusters(items, gap_hours=12, gps_km=30)] == [3]


def test_split_by_gps_jump_even_without_time_gap():
    t = datetime(2024, 5, 1, 9)
    items = _items((t, HYD), (t + timedelta(hours=1), None), (t + timedelta(hours=2), GOA))
    assert haversine_km(HYD, GOA) > 400
    assert [len(c) for c in split_clusters(items, gap_hours=6, gps_km=30)] == [2, 1]


def test_null_island_gps_is_ignored():
    t = datetime(2024, 5, 1, 9)
    items = _items((t, HYD), (t + timedelta(hours=1), (0.0, 0.0)), (t + timedelta(hours=2), HYD))
    assert len(split_clusters(items, 6, 30)) == 1


# ---------- occasions ----------

def test_ordinals_and_leap_birthdays():
    assert [ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 101)] == [
        "1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "101st"]
    assert on_year(2, 29, 2023) == date(2023, 2, 28)
    assert on_year(2, 29, 2024) == date(2024, 2, 29)


def test_builtin_festival_table_is_complete_and_plausible():
    table = builtin_table()
    assert set(table) == set(FESTIVALS)
    months = {"sankranti": {1}, "ugadi": {3, 4}, "holi": {2, 3}, "raksha_bandhan": {7, 8},
              "ganesh_chaturthi": {8, 9}, "dussehra": {9, 10}, "diwali": {10, 11}}
    for key, years in table.items():
        assert sorted(map(int, years)) == list(range(2000, 2031)), key
        for y, entry in years.items():
            d = date.fromisoformat(entry["date"])
            assert d.year == int(y) and d.month in months[key], (key, y, d)
            assert date.fromisoformat(entry.get("start", entry["date"])) <= d <= date.fromisoformat(
                entry.get("end", entry["date"]))
    # spot checks against published dates (Telugu states)
    assert table["diwali"]["2022"]["date"] == "2022-10-24"
    assert table["ugadi"]["2024"]["date"] == "2024-04-09"
    assert table["sankranti"]["2025"] == {"date": "2025-01-14", "start": "2025-01-13", "end": "2025-01-15"}


def test_occasion_index_labels(data_dir):
    with SessionLocal() as s:
        seed_festivals(s)
        s.add(Person(name="Aadhya", birth_date=date(2021, 10, 24)))
        s.commit()
        idx = OccasionIndex(s)
        hits = idx.between(date(2022, 10, 24), date(2022, 10, 24))
        names = [h.name for h in hits]
        assert names == ["Aadhya's 1st birthday", "Deepavali 2022"]  # family first
        assert [h.name for h in idx.between(date(2021, 10, 24), date(2021, 10, 24))][0] == "Aadhya is born"
        assert not [h for h in idx.between(date(2020, 10, 24), date(2020, 10, 24)) if h.kind == "birthday"]
        # Sankranti covers Bhogi..Kanuma
        assert [h.name for h in idx.between(date(2025, 1, 13), date(2025, 1, 13))] == ["Sankranti 2025"]


# ---------- rebuild with a fake library ----------

@pytest.fixture
def library(data_dir):
    """Day trip (5 photos), a weekend 3 days later (4), 2 stray photos in June, 1 on Diwali 2022."""
    rng = np.random.default_rng(1)
    plan = []
    t = datetime(2022, 3, 5, 10)
    plan += [t + timedelta(minutes=30 * i) for i in range(5)]
    t = datetime(2022, 3, 8, 9)
    plan += [t + timedelta(hours=3 * i) for i in range(4)]
    plan += [datetime(2022, 6, 3, 18), datetime(2022, 6, 20, 11)]
    plan += [datetime(2022, 10, 24, 19)]
    with SessionLocal() as s:
        seed_festivals(s)
        folder = SourceFolder(path="X:/fake")
        s.add(folder)
        s.flush()
        ids = []
        for i, when in enumerate(plan):
            m = Media(folder_id=folder.id, rel_path=f"{i}.jpg", filename=f"{i}.jpg", ext=".jpg", kind="photo",
                      size=1, mtime_ns=1, taken_at=when, date_source="exif", date_confidence="high",
                      width=400, height=300, has_thumb=True, phash=f"{rng.integers(0, 2**63):016x}")
            s.add(m)
            s.flush()
            s.add(Quality(media_id=m.id, version=2, media_mtime_ns=1, sharpness_raw=1, sharpness=0.8,
                          exposure=0.8, resolution=0.8, total=50 + i))
            v = rng.normal(size=512).astype(np.float32)
            s.add(ClipEmbedding(media_id=m.id, model="t", vector=(v / np.linalg.norm(v)).tobytes()))
            ids.append(m.id)
        s.commit()
    return ids


def _events(s):
    out = {}
    for e in s.scalars(select(Event).order_by(Event.start_at)):
        out[e.id] = (e.kind, sorted(s.scalars(select(EventMedia.media_id).where(EventMedia.event_id == e.id))))
    return out


def test_rebuild_groups_small_clusters_into_monthly_moments(library):
    with SessionLocal() as s:
        rebuild_events(s)
        evs = list(_events(s).values())
    assert evs == [
        ("auto", library[0:5]),
        ("auto", library[5:9]),
        ("moments", library[9:11]),
        ("auto", [library[11]]),  # a lone photo on Diwali still gets its own event
    ]


def test_rebuild_is_stable_and_keeps_user_edits(library):
    with SessionLocal() as s:
        rebuild_events(s)
        first = _events(s)
        rebuild_events(s)
        assert _events(s) == first  # same ids, same members

        trip = next(eid for eid, (_k, m) in first.items() if m == library[0:5])
        weekend = next(eid for eid, (_k, m) in first.items() if m == library[5:9])
        # user renames the trip (locks it) and moves one weekend photo into it
        s.get(Event, trip).title, s.get(Event, trip).locked = "Golconda Fort", True
        em = s.get(EventMedia, library[5])
        em.event_id, em.assigned_by = trip, "user"
        s.commit()

        # an edited photo (new time) is still regrouped automatically
        s.query(Media).filter(Media.id == library[6]).update({Media.taken_at: datetime(2022, 3, 8, 19)})
        s.commit()
        rebuild_events(s)
        after = _events(s)
        assert after[trip][1] == sorted(library[0:6])
        assert s.get(Event, trip).title == "Golconda Fort"
        assert weekend in after and library[5] not in after[weekend][1]


def test_new_photo_inside_locked_window_joins_it(library):
    with SessionLocal() as s:
        rebuild_events(s)
        trip = next(e for e in s.scalars(select(Event)) if e.start_at == datetime(2022, 3, 5, 10))
        trip.locked = True
        s.commit()
        folder = s.scalars(select(SourceFolder)).first()
        new = Media(folder_id=folder.id, rel_path="new.jpg", filename="new.jpg", ext=".jpg", kind="photo",
                    size=1, mtime_ns=1, taken_at=datetime(2022, 3, 5, 11, 15), date_source="exif",
                    date_confidence="high")
        s.add(new)
        s.commit()
        rebuild_events(s)
        assert s.get(EventMedia, new.id).event_id == trip.id


# ---------- curation ----------

def test_curate_skips_lookalikes_and_hidden_copies(library):
    with SessionLocal() as s:
        # photo 1 becomes a near-copy of photo 0 (same CLIP vector)
        v0 = s.get(ClipEmbedding, library[0]).vector
        s.get(ClipEmbedding, library[1]).vector = v0
        s.commit()
        ctx = CurateContext(s, library[0:5])
        hero, picks = ctx.curate(library[0:5], limit=12)
    assert len(picks) == 4 and not {library[0], library[1]} <= set(picks)
    assert hero in picks
    assert picks == sorted(picks)  # time order


def test_curate_respects_limit(library):
    with SessionLocal() as s:
        _hero, picks = CurateContext(s).curate(library, limit=5)
    assert len(picks) == 5
    assert set(picks) == set(library[-5:])  # the highest quality ones (total = 50 + i)


def test_tag_probabilities_softmax():
    classes = np.eye(3, dtype=np.float32)
    p = tag_probabilities(np.array([[1, 0, 0]], dtype=np.float32), classes)
    assert p.shape == (1, 3) and abs(p.sum() - 1) < 1e-6 and p[0, 0] > 0.99


# ---------- API ----------

@pytest.fixture
def client(library, data_dir, monkeypatch):
    from app.main import app

    monkeypatch.setenv("FM_DATA_DIR", str(data_dir))  # app startup must reuse the temp data folder
    with TestClient(app) as c:
        with SessionLocal() as s:
            rebuild_events(s)
        yield c


def test_events_api_edit_flow(client, library):
    evs = client.get("/api/events", params={"order": "asc"}).json()["events"]
    assert [e["kind"] for e in evs] == ["auto", "auto", "moments", "auto"]
    assert evs[2]["title"] == "Moments · June 2022"
    assert evs[3]["title"] == "Deepavali 2022"
    trip, weekend = evs[0]["id"], evs[1]["id"]

    d = client.patch(f"/api/events/{trip}", json={"title": "Golconda Fort"}).json()
    assert d["title"] == "Golconda Fort" and d["locked"]
    assert 1 <= len(d["curated"]) <= 12 and d["hero_media_id"] in [m["id"] for m in d["media"]]

    d = client.patch(f"/api/events/{trip}", json={"hero_media_id": library[2]}).json()
    assert d["hero_media_id"] == library[2] and d["hero_by_user"]

    merged = client.post("/api/events/merge", json={"event_ids": [trip, weekend]}).json()
    assert merged["id"] == trip and merged["photo_count"] == 9 and merged["title"] == "Golconda Fort"

    split = client.post(f"/api/events/{trip}/split", json={"media_id": library[5]}).json()
    assert split["event"]["photo_count"] == 5
    assert client.get(f"/api/events/{split['new_event_id']}").json()["photo_count"] == 4

    moved = client.post("/api/events/move", json={"media_ids": [library[9]], "event_id": None,
                                                  "new_title": "Park"}).json()
    assert client.get(f"/api/events/{moved['event_id']}").json()["title"] == "Park"

    custom = client.post("/api/events", json={"title": "Summer", "start": "2022-06-01", "end": "2022-06-30"}).json()
    assert custom["kind"] == "custom" and custom["photo_count"] == 1  # the photo moved by hand stays in "Park"

    years = client.get("/api/occasions/festival/diwali/years").json()
    assert years and years[0]["year"] == 2022

    assert client.delete(f"/api/events/{custom['id']}").status_code == 200
    assert all(e["id"] != custom["id"] for e in client.get("/api/events").json()["events"])


def test_occasions_and_festivals_api(client):
    r = client.post("/api/occasions", json={"kind": "anniversary", "name": "Amma & Nanna", "month": 3,
                                            "day": 8, "year": 2012})
    assert r.status_code == 201
    occ = r.json()
    evs = client.get("/api/events", params={"order": "asc"}).json()["events"]
    weekend = evs[1]
    assert weekend["title"] == "Amma & Nanna: 10th anniversary"
    assert client.post("/api/occasions", json={"kind": "birthday", "name": "x", "month": 2, "day": 30}).status_code == 422

    f = client.get("/api/festivals", params={"year": 2022}).json()
    assert [x["festival"] for x in f["festivals"]][0] == "sankranti" and len(f["festivals"]) == 7
    diwali = next(x for x in f["festivals"] if x["festival"] == "diwali")
    assert diwali["events"] and diwali["start"] == "2022-10-23"
    edited = client.patch(f"/api/festivals/{diwali['id']}", json={"date": "2022-10-25"}).json()
    assert edited["user_edited"] and edited["start"] == "2022-10-24"
    reset = client.post(f"/api/festivals/{diwali['id']}/reset").json()
    assert reset["date"] == "2022-10-24" and not reset["user_edited"]

    assert client.delete(f"/api/occasions/{occ['id']}").json()["ok"]
