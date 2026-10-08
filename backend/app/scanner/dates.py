"""Capture-date detection.

Priority: EXIF DateTimeOriginal -> video container creation time ->
filename patterns -> file modified time.
"""

import re
from dataclasses import dataclass
from datetime import datetime

MIN_YEAR = 1980


@dataclass(frozen=True)
class DateResult:
    taken_at: datetime
    source: str  # exif | video_meta | filename | mtime
    confidence: str  # high | medium | low


def _plausible(dt: datetime) -> bool:
    return MIN_YEAR <= dt.year <= datetime.now().year + 1


def _make(y, mo, d, h=0, mi=0, s=0) -> datetime | None:
    try:
        dt = datetime(int(y), int(mo), int(d), int(h), int(mi), int(s))
    except ValueError:
        return None
    return dt if _plausible(dt) else None


_EXIF_RE = re.compile(r"\s*(\d{4})[:\-](\d{2})[:\-](\d{2})[ T](\d{2}):(\d{2}):(\d{2})")


def parse_exif_datetime(value: str | bytes | None) -> datetime | None:
    """Parse 'YYYY:MM:DD HH:MM:SS'. Returns None for blanks like '0000:00:00 00:00:00'."""
    if not value:
        return None
    if isinstance(value, bytes):
        value = value.decode(errors="ignore")
    m = _EXIF_RE.match(str(value))
    return _make(*m.groups()) if m else None


# WhatsApp Image 2023-05-14 at 18.32.10 / WhatsApp Image 2023-05-14 at 6.32.10 PM
_WHATSAPP_LONG = re.compile(
    r"WhatsApp (?:Image|Video|Audio) (\d{4})-(\d{2})-(\d{2}) at "
    r"(\d{1,2})\.(\d{2})\.(\d{2})(?:\s*([AP]M))?",
    re.IGNORECASE,
)
# IMG-20230514-WA0012
_WHATSAPP_SHORT = re.compile(r"(?:IMG|VID|AUD|PTT|STK)-(\d{4})(\d{2})(\d{2})-WA\d+", re.IGNORECASE)
# IMG_20230514_183210, VID_20230514_183210, PXL_20230514_183210123, 20230514_183210
_COMPACT_DATETIME = re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})[_\-T ]?(\d{2})(\d{2})(\d{2})")
# Screenshot_2023-05-14-18-32-10, 2023-05-14 18.32.10
_DASHED_DATETIME = re.compile(
    r"(?<!\d)(\d{4})-(\d{2})-(\d{2})[ _\-T](\d{2})[.\-:](\d{2})[.\-:](\d{2})"
)
_DASHED_DATE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_COMPACT_DATE = re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)")


def date_from_filename(name: str) -> datetime | None:
    m = _WHATSAPP_LONG.search(name)
    if m:
        y, mo, d, h, mi, s, ampm = m.groups()
        hour = int(h)
        if ampm:
            hour = hour % 12 + (12 if ampm.upper() == "PM" else 0)
        dt = _make(y, mo, d, hour, mi, s)
        if dt:
            return dt

    for pattern in (_WHATSAPP_SHORT, _COMPACT_DATETIME, _DASHED_DATETIME):
        for m in pattern.finditer(name):
            dt = _make(*m.groups())
            if dt:
                return dt

    for pattern in (_DASHED_DATE, _COMPACT_DATE):
        for m in pattern.finditer(name):
            dt = _make(*m.groups())
            if dt:
                return dt
    return None


def detect_date(
    filename: str,
    mtime: float,
    exif_value: str | bytes | None = None,
    video_created: datetime | None = None,
) -> DateResult:
    dt = parse_exif_datetime(exif_value)
    if dt:
        return DateResult(dt, "exif", "high")
    if video_created and _plausible(video_created):
        return DateResult(video_created, "video_meta", "high")
    dt = date_from_filename(filename)
    if dt:
        return DateResult(dt, "filename", "medium")
    return DateResult(datetime.fromtimestamp(mtime).replace(microsecond=0), "mtime", "low")
