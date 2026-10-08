import os
from datetime import datetime

from PIL import Image
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Media, SourceFolder
from app.scanner.scan import create_job, run_scan
from app.scanner.thumbs import thumb_path

from .conftest import snapshot


def _add_folder(path) -> int:
    with SessionLocal() as s:
        f = SourceFolder(path=str(path))
        s.add(f)
        s.commit()
        return f.id


def _scan():
    with SessionLocal() as s:
        job = create_job(s)
    return run_scan(job.id)


def _media() -> dict[str, Media]:
    with SessionLocal() as s:
        return {m.rel_path: m for m in s.scalars(select(Media)).all()}


def test_scan_detects_dates_and_leaves_sources_untouched(data_dir, sample_folder):
    before = snapshot(sample_folder)
    _add_folder(sample_folder)

    job = _scan()

    assert job.status == "done"
    assert (job.total, job.added, job.updated, job.unchanged) == (8, 8, 0, 0)
    assert job.errors == 1  # broken.jpg

    media = _media()
    assert ".hidden/skip.jpg" not in media
    assert "notes.txt" not in media

    m = media["DSC_0001.jpg"]
    assert (m.date_source, m.date_confidence) == ("exif", "high")
    assert m.taken_at == datetime(2019, 8, 15, 10, 20, 30)
    assert (m.width, m.height) == (480, 640)  # orientation 6 -> portrait
    assert m.camera == "Canon EOS 200D"

    assert media["IMG-20200102-WA0003.jpg"].taken_at == datetime(2020, 1, 2)
    assert media["IMG-20200102-WA0003.jpg"].date_source == "filename"
    assert media["WhatsApp Image 2021-03-04 at 5.06.07 PM.jpeg"].taken_at == datetime(2021, 3, 4, 17, 6, 7)
    assert media["2022/trip/IMG_20220506_070809.png"].taken_at == datetime(2022, 5, 6, 7, 8, 9)
    assert media["random.webp"].date_source == "mtime"
    assert media["random.webp"].taken_at == datetime(2018, 6, 1, 12, 0, 0)
    assert media["phone.heic"].has_thumb

    v = media["VID_20230102_030405.mp4"]
    assert v.kind == "video"
    assert v.has_thumb and v.duration_s and v.duration_s > 1

    broken = media["broken.jpg"]
    assert broken.error and not broken.has_thumb and broken.date_source == "mtime"

    for m in media.values():
        assert len(m.sha256) == 64
        if m.has_thumb:
            assert thumb_path(m.id).is_file()
            assert thumb_path(m.id).is_relative_to(data_dir)

    # The golden rule: originals byte-identical, nothing added or removed in the source tree
    assert snapshot(sample_folder) == before


def test_incremental_rescan(data_dir, sample_folder):
    _add_folder(sample_folder)
    _scan()
    before = snapshot(sample_folder)

    job = _scan()
    assert (job.added, job.updated, job.unchanged, job.missing) == (0, 0, 8, 0)
    assert snapshot(sample_folder) == before

    # The test (not the app) changes the source folder to simulate new/edited/deleted files
    Image.new("RGB", (100, 100), "white").save(sample_folder / "IMG_20240101_101010.jpg")
    edited = sample_folder / "random.webp"
    Image.new("RGB", (120, 80), "pink").save(edited)
    os.utime(edited, (datetime(2017, 3, 3).timestamp(),) * 2)
    (sample_folder / "phone.heic").unlink()
    before = snapshot(sample_folder)

    job = _scan()
    assert (job.added, job.updated, job.unchanged, job.missing) == (1, 1, 6, 1)
    media = _media()
    assert media["phone.heic"].missing
    assert media["random.webp"].taken_at == datetime(2017, 3, 3)
    assert media["IMG_20240101_101010.jpg"].taken_at == datetime(2024, 1, 1, 10, 10, 10)
    assert snapshot(sample_folder) == before


def test_missing_folder_does_not_mark_media_missing(data_dir, sample_folder, tmp_path):
    _add_folder(sample_folder)
    _scan()
    renamed = tmp_path / "unplugged"
    sample_folder.rename(renamed)  # simulate an unplugged drive

    job = _scan()
    assert job.status == "done" and "not found" in job.message
    assert not any(m.missing for m in _media().values())
