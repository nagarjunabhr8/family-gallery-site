from datetime import datetime

import pytest

from app.scanner.dates import date_from_filename, detect_date, parse_exif_datetime


@pytest.mark.parametrize(
    "name, expected",
    [
        ("IMG-20230514-WA0012.jpg", datetime(2023, 5, 14)),
        ("VID-20190101-WA0001.mp4", datetime(2019, 1, 1)),
        ("IMG_20230514_183210.jpg", datetime(2023, 5, 14, 18, 32, 10)),
        ("VID_20230514_183210.mp4", datetime(2023, 5, 14, 18, 32, 10)),
        ("PXL_20230514_183210123.jpg", datetime(2023, 5, 14, 18, 32, 10)),
        ("20230514_183210.jpg", datetime(2023, 5, 14, 18, 32, 10)),
        ("WhatsApp Image 2023-05-14 at 18.32.10.jpeg", datetime(2023, 5, 14, 18, 32, 10)),
        ("WhatsApp Image 2023-05-14 at 6.32.10 PM.jpeg", datetime(2023, 5, 14, 18, 32, 10)),
        ("WhatsApp Image 2023-05-14 at 12.05.00 AM (1).jpeg", datetime(2023, 5, 14, 0, 5, 0)),
        ("WhatsApp Video 2022-11-02 at 9.15.30 AM.mp4", datetime(2022, 11, 2, 9, 15, 30)),
        ("Screenshot_2023-05-14-18-32-10.png", datetime(2023, 5, 14, 18, 32, 10)),
        ("scan 20101225.jpg", datetime(2010, 12, 25)),
        ("Diwali 2015-11-11.jpg", datetime(2015, 11, 11)),
    ],
)
def test_filename_patterns(name, expected):
    assert date_from_filename(name) == expected


@pytest.mark.parametrize(
    "name",
    [
        "DSC_0001.jpg",
        "IMG_1234.HEIC",
        "photo.jpg",
        "IMG_20231345_101010.jpg",  # month 13
        "12345678.jpg",  # year 1234 implausible
        "IMG_99991231_000000.jpg",  # far future
    ],
)
def test_filename_without_valid_date(name):
    assert date_from_filename(name) is None


def test_exif_parse():
    assert parse_exif_datetime("2019:08:15 10:20:30") == datetime(2019, 8, 15, 10, 20, 30)
    assert parse_exif_datetime(b"2019:08:15 10:20:30\x00") == datetime(2019, 8, 15, 10, 20, 30)
    assert parse_exif_datetime("0000:00:00 00:00:00") is None
    assert parse_exif_datetime("    :  :     :  :  ") is None
    assert parse_exif_datetime(None) is None


def test_priority_exif_beats_filename():
    r = detect_date("IMG-20200101-WA0001.jpg", 0, exif_value="2019:08:15 10:20:30")
    assert (r.source, r.confidence, r.taken_at) == ("exif", "high", datetime(2019, 8, 15, 10, 20, 30))


def test_priority_video_meta_beats_filename():
    r = detect_date("VID_20200101_000000.mp4", 0, video_created=datetime(2021, 2, 3, 4, 5, 6))
    assert (r.source, r.taken_at) == ("video_meta", datetime(2021, 2, 3, 4, 5, 6))


def test_priority_filename_beats_mtime():
    r = detect_date("IMG-20200101-WA0001.jpg", datetime(2024, 1, 1).timestamp(), exif_value="garbage")
    assert (r.source, r.confidence, r.taken_at) == ("filename", "medium", datetime(2020, 1, 1))


def test_fallback_mtime():
    ts = datetime(2018, 6, 1, 12, 0, 0).timestamp()
    r = detect_date("DSC_0001.jpg", ts)
    assert (r.source, r.confidence, r.taken_at) == ("mtime", "low", datetime(2018, 6, 1, 12, 0, 0))
