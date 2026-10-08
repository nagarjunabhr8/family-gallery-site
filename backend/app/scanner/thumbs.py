"""Thumbnails, stored as WebP in <data>/thumbs/. Never written next to originals."""

import io
from pathlib import Path

from PIL import Image, ImageOps

from ..config import THUMB_MAX_EDGE
from ..safety import data_dir, safe_unlink, safe_write_bytes


def thumb_path(media_id: int) -> Path:
    return data_dir() / "thumbs" / f"{media_id // 1000:04d}" / f"{media_id}.webp"


def make_thumbnail(img: Image.Image) -> Image.Image:
    """Return an upright, downscaled in-memory copy of `img`."""
    img = ImageOps.exif_transpose(img)
    img.thumbnail((THUMB_MAX_EDGE, THUMB_MAX_EDGE), Image.Resampling.LANCZOS)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
    return img


def save_thumbnail(thumb: Image.Image, media_id: int) -> Path:
    buf = io.BytesIO()
    thumb.save(buf, "WEBP", quality=80, method=4)
    return safe_write_bytes(thumb_path(media_id), buf.getvalue())


def delete_thumbnail(media_id: int) -> None:
    safe_unlink(thumb_path(media_id))
