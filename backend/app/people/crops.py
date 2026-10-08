"""Small square face crops for the People UI, stored in <data>/faces/."""

import io
from pathlib import Path

from PIL import Image

from ..safety import data_dir, safe_unlink, safe_write_bytes

CROP_PX = 192


def crop_path(face_id: int) -> Path:
    return data_dir() / "faces" / f"{face_id // 1000:04d}" / f"{face_id}.webp"


def make_crop(img: Image.Image, box: tuple[float, float, float, float]) -> Image.Image:
    """Square crop around a face box (pixels), padded 1.6x, from the upright image."""
    x1, y1, x2, y2 = box
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    half = max(x2 - x1, y2 - y1) * 0.8
    crop = img.crop((round(cx - half), round(cy - half), round(cx + half), round(cy + half)))
    return crop.resize((CROP_PX, CROP_PX), Image.Resampling.LANCZOS)


def save_crop(crop: Image.Image, face_id: int) -> Path:
    buf = io.BytesIO()
    crop.convert("RGB").save(buf, "WEBP", quality=82)
    return safe_write_bytes(crop_path(face_id), buf.getvalue())


def delete_crop(face_id: int) -> None:
    safe_unlink(crop_path(face_id))
