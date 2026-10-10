"""Whole pipeline on the generated sample set: scan -> analyse -> duplicates -> events.

Proves the source folder is byte-for-byte unchanged (SHA-256, size, mtime) and
that nothing was written into it.
"""

import sys
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select

from app.analysis.grouping import set_best
from app.analysis.run import run_analysis
from app.api.events import Presenter
from app.db import SessionLocal
from app.models import DupGroup, DupMember, Event, Media, SourceFolder
from app.occasions.festivals import seed_festivals
from app.scanner.scan import create_job, run_scan

from .conftest import snapshot

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import make_sample_photos  # noqa: E402

TODAY = date(2026, 10, 8)


@pytest.fixture
def library(data_dir, tmp_path):
    src = tmp_path / "photos"
    make_sample_photos.build(src, TODAY)
    before = snapshot(src)
    with SessionLocal() as s:
        seed_festivals(s)
        s.add(SourceFolder(path=str(src)))
        s.commit()
    yield src, before
    assert snapshot(src) == before, "source folder changed"


def _scan_and_analyse():
    with SessionLocal() as s:
        scan = create_job(s)
    scan = run_scan(scan.id)
    with SessionLocal() as s:
        job = create_job(s, kind="analyze")
    return scan, run_analysis(job.id)


def _groups(s) -> list[tuple[str, list[str]]]:
    out = []
    for g in s.scalars(select(DupGroup)):
        paths = sorted(s.scalars(
            select(Media.rel_path).join(DupMember, DupMember.media_id == Media.id).where(DupMember.group_id == g.id)
        ))
        out.append((g.kind, paths))
    return sorted(out, key=lambda x: x[1])


def test_full_pipeline_on_sample_set(library):
    src, _before = library
    scan, analysis = _scan_and_analyse()
    # 27 files - notes.txt - hidden; broken.jpg is recorded as the one problem
    assert (scan.status, scan.added, scan.errors) == ("done", 25, 1)
    assert analysis.status == "done"

    with SessionLocal() as s:
        media = {m.rel_path: m for m in s.scalars(select(Media))}
        assert ".hidden/skip.jpg" not in media and "Misc/notes.txt" not in media
        assert media["Misc/broken.jpg"].error is not None
        assert (media["Festivals/IMG_20221024_190000.jpg"].date_source, media["Festivals/IMG_20221024_190000.jpg"].date_confidence) == ("exif", "high")
        assert media["WhatsApp/IMG-20210307-WA0003.jpg"].date_source == "filename"
        assert media["Misc/scan.png"].date_source == "mtime"
        assert media["2024/VID_20240102_030405.mp4"].kind == "video"

        groups = _groups(s)
        paths = [p for _k, ps in groups for p in ps]
        # the burst, and the party photo with its byte-identical backup and recompressed copy
        assert ["2023/IMG_20230610_111501.jpg", "2023/IMG_20230610_111503.jpg", "2023/IMG_20230610_111505.jpg"] in [g[1] for g in groups]
        party = next(ps for _k, ps in groups if "Backup/IMG_20230610_143000.jpg" in ps)
        assert {"2023/IMG_20230610_143000.jpg", "Edited/party_small.jpg"} <= set(party)
        # distinct photos are never grouped
        assert not any(p.startswith("2019 Trip/") or p.startswith("Festivals/") for p in paths)

        events = s.scalars(select(Event).order_by(Event.start_at)).all()
        titles = {d["title"]: d for d in map(Presenter(s, [e.id for e in events]).summary, events)}
        assert titles["Deepavali 2022"]["photo_count"] == 3
        assert any(t.startswith("Moments · ") for t in titles)

    # nothing new appeared in the source folder (no thumbnails, caches, sidecars)
    assert not [p for p in src.rglob("*") if p.suffix in {".webp", ".db", ".tmp"} and p.name != "sticker.webp"]


def test_rescan_is_incremental_and_keeps_best_pick(library):
    _scan_and_analyse()
    with SessionLocal() as s:
        g = next(g for g in s.scalars(select(DupGroup)) if g.size == 3 and g.kind)
        others = [mid for (mid,) in s.execute(select(DupMember.media_id).where(DupMember.group_id == g.id)) if mid != g.best_media_id]
        set_best(s, g, others[0])
        chosen = others[0]

    scan, analysis = _scan_and_analyse()
    assert (scan.added, scan.updated, scan.unchanged) == (0, 0, 25)
    assert analysis.updated == 0  # nothing re-analysed
    with SessionLocal() as s:
        g = s.scalars(select(DupGroup).join(DupMember, DupMember.group_id == DupGroup.id).where(DupMember.media_id == chosen)).one()
        assert g.best_media_id == chosen
