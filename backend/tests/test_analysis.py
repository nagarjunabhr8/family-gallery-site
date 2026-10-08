"""End-to-end Phase 2: scan -> analyze -> groups, user choice survives, sources untouched."""

import shutil

from PIL import Image
from sqlalchemy import select

from app.analysis.grouping import set_best
from app.analysis.run import regroup_from_settings, run_analysis
from app.db import SessionLocal
from app.models import DupGroup, DupMember, Media, Quality, SourceFolder
from app.scanner.scan import create_job, run_scan

from .conftest import _jpeg, pattern, snapshot


def _setup(folder) -> None:
    with SessionLocal() as s:
        s.add(SourceFolder(path=str(folder)))
        s.commit()
        scan = create_job(s)
    assert run_scan(scan.id).status == "done"
    with SessionLocal() as s:
        job = create_job(s, kind="analyze")
    result = run_analysis(job.id)
    assert result.status == "done", result.message


def _groups():
    with SessionLocal() as s:
        out = {}
        for g in s.scalars(select(DupGroup)):
            names = sorted(
                s.scalars(select(Media.filename).join(DupMember, DupMember.media_id == Media.id)
                          .where(DupMember.group_id == g.id))
            )
            best = s.get(Media, g.best_media_id).filename
            out[tuple(names)] = (g.kind, best)
        return out


def test_analysis_groups_duplicates(data_dir, sample_folder):
    # exact copy, a downscaled near-copy, and a 2-shot burst in the same minute
    shutil.copy2(sample_folder / "DSC_0001.jpg", sample_folder / "DSC_0001 - Copy.jpg")
    pattern(3, (320, 240)).save(sample_folder / "small_copy.jpg", quality=70)  # near-copy of the WhatsApp image
    _jpeg(sample_folder / "burst_a.jpg", 20, exif_dt="2024:05:05 09:30:10")
    burst_b = pattern(20).transpose(Image.Transpose.FLIP_LEFT_RIGHT)  # same scene, slightly different framing
    burst_b.crop((40, 0, 640, 480)).resize((640, 480)).save(
        sample_folder / "burst_b.jpg", exif=_burst_exif("2024:05:05 09:30:41"),
    )
    before = snapshot(sample_folder)

    _setup(sample_folder)

    groups = _groups()
    assert groups[("DSC_0001 - Copy.jpg", "DSC_0001.jpg")][0] == "exact"
    assert groups[("WhatsApp Image 2021-03-04 at 5.06.07 PM.jpeg", "small_copy.jpg")] == (
        "near", "WhatsApp Image 2021-03-04 at 5.06.07 PM.jpeg",  # higher resolution wins
    )

    with SessionLocal() as s:
        n_quality = s.scalar(select(Quality).limit(1))
        assert n_quality is not None and 0 <= n_quality.total <= 100
        assert all(m.phash for m in s.scalars(select(Media).where(Media.kind == "photo", Media.has_thumb)))

    assert snapshot(sample_folder) == before


def _burst_exif(dt: str) -> bytes:
    exif = Image.Exif()
    exif.get_ifd(0x8769)[36867] = dt
    return exif.tobytes()


def test_user_choice_survives_regroup_and_reanalysis(data_dir, sample_folder):
    pattern(3, (320, 240)).save(sample_folder / "small_copy.jpg", quality=70)
    _setup(sample_folder)

    with SessionLocal() as s:
        group = s.scalars(select(DupGroup)).one()
        small = s.scalars(select(Media).where(Media.filename == "small_copy.jpg")).one()
        assert group.best_media_id != small.id
        set_best(s, group, small.id)

    with SessionLocal() as s:
        regroup_from_settings(s)
        group = s.scalars(select(DupGroup)).one()
        assert s.get(Media, group.best_media_id).filename == "small_copy.jpg"

        set_best(s, group, None)  # back to automatic
        group = s.scalars(select(DupGroup)).one()
        assert s.get(Media, group.best_media_id).filename != "small_copy.jpg"


def test_unchanged_photos_are_not_reanalysed(data_dir, sample_folder):
    _setup(sample_folder)
    with SessionLocal() as s:
        job = create_job(s, kind="analyze")
    again = run_analysis(job.id)
    assert again.status == "done" and again.total == 0 and again.unchanged > 0
