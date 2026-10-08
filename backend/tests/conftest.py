import hashlib
import os
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import pillow_heif
import pytest
from PIL import Image

from app import db, safety

pillow_heif.register_heif_opener()

FIXED_MTIME = datetime(2018, 6, 1, 12, 0, 0).timestamp()


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    d = safety.set_data_dir(tmp_path / "data")
    db.init_db(d)
    yield d
    db.engine.dispose()


def pattern(seed: int, size=(640, 480)) -> Image.Image:
    """A distinct, photo-like test image (smooth random blobs) for each seed."""
    rng = np.random.default_rng(seed)
    small = rng.integers(0, 256, (6, 8, 3), dtype=np.uint8)
    img = Image.fromarray(small).resize(size, Image.Resampling.BICUBIC)
    return img


def _jpeg(path: Path, seed: int, exif_dt: str | None = None, size=(640, 480), orientation=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    img = pattern(seed, size)
    exif = Image.Exif()
    if exif_dt:
        exif.get_ifd(0x8769)[36867] = exif_dt
        exif[271], exif[272] = "Canon", "Canon EOS 200D"
    if orientation:
        exif[274] = orientation
    img.save(path, "JPEG", exif=exif.tobytes())


def _video(path: Path, frames=30, size=(320, 240)):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 15, size)
    for i in range(frames):
        frame = np.full((size[1], size[0], 3), (i * 8) % 255, dtype=np.uint8)
        writer.write(frame)
    writer.release()


@pytest.fixture
def sample_folder(tmp_path: Path) -> Path:
    """A small source folder covering each date-detection path."""
    root = tmp_path / "photos"
    _jpeg(root / "DSC_0001.jpg", 1, exif_dt="2019:08:15 10:20:30", orientation=6)
    _jpeg(root / "IMG-20200102-WA0003.jpg", 2)
    _jpeg(root / "WhatsApp Image 2021-03-04 at 5.06.07 PM.jpeg", 3)
    sub = root / "2022" / "trip"
    sub.mkdir(parents=True)
    pattern(4, (300, 200)).save(sub / "IMG_20220506_070809.png")
    pattern(5, (300, 200)).save(root / "random.webp")
    pattern(6, (300, 200)).save(root / "phone.heic")
    _video(root / "VID_20230102_030405.mp4")
    (root / "broken.jpg").write_bytes(b"this is not a jpeg")
    (root / "notes.txt").write_text("not media")
    (root / ".hidden").mkdir()
    _jpeg(root / ".hidden" / "skip.jpg", 7)

    for p in root.rglob("*"):
        if p.is_file():
            os.utime(p, (FIXED_MTIME, FIXED_MTIME))
    return root


def snapshot(root: Path) -> dict[str, tuple[int, int, str]]:
    """rel_path -> (size, mtime_ns, sha256) for every file under root."""
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            st = p.stat()
            out[p.relative_to(root).as_posix()] = (
                st.st_size,
                st.st_mtime_ns,
                hashlib.sha256(p.read_bytes()).hexdigest(),
            )
    return out
