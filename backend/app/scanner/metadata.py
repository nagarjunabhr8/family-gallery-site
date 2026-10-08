"""Photo metadata (EXIF, dimensions, GPS) and file hashing. Read-only."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pillow_heif
from PIL import Image

from ..safety import open_source

pillow_heif.register_heif_opener()
Image.MAX_IMAGE_PIXELS = 250_000_000

IFD_EXIF = 0x8769
IFD_GPS = 0x8825
TAG_DATETIME_ORIGINAL = 36867
TAG_DATETIME_DIGITIZED = 36868
TAG_ORIENTATION = 274
TAG_MAKE = 271
TAG_MODEL = 272


@dataclass
class ImageInfo:
    width: int
    height: int
    orientation: int | None = None
    exif_datetime: str | None = None
    camera: str | None = None
    gps_lat: float | None = None
    gps_lon: float | None = None


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open_source(path) as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def _text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode(errors="ignore")
    value = str(value).strip("\x00 ").strip()
    return value or None


def _gps_coord(values, ref) -> float | None:
    try:
        d, m, s = (float(v) for v in values)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    coord = d + m / 60 + s / 3600
    if _text(ref) in ("S", "W"):
        coord = -coord
    return coord


def read_image_info(img: Image.Image) -> ImageInfo:
    """Extract metadata from an opened (not necessarily loaded) image."""
    width, height = img.size
    info = ImageInfo(width=width, height=height)
    try:
        exif = img.getexif()
    except Exception:
        return info

    info.orientation = exif.get(TAG_ORIENTATION)
    if info.orientation in (5, 6, 7, 8):  # rotated 90/270 for display
        info.width, info.height = height, width

    sub = exif.get_ifd(IFD_EXIF)
    info.exif_datetime = _text(sub.get(TAG_DATETIME_ORIGINAL)) or _text(sub.get(TAG_DATETIME_DIGITIZED))

    make, model = _text(exif.get(TAG_MAKE)), _text(exif.get(TAG_MODEL))
    if model and make and model.lower().startswith(make.lower()):
        info.camera = model
    else:
        info.camera = " ".join(p for p in (make, model) if p) or None

    gps = exif.get_ifd(IFD_GPS)
    if gps:
        lat, lon = _gps_coord(gps.get(2), gps.get(1)), _gps_coord(gps.get(4), gps.get(3))
        if lat is not None and lon is not None and not (lat == 0 and lon == 0):
            info.gps_lat, info.gps_lon = round(lat, 6), round(lon, 6)
    return info
