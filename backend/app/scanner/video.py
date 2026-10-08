"""Video metadata: MP4/MOV container creation time and a preview frame. Read-only."""

import os
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import cv2
from PIL import Image

from ..safety import open_source

# Seconds between 1904-01-01 (QuickTime epoch) and 1970-01-01
_QT_EPOCH_OFFSET = 2_082_844_800


@dataclass
class VideoInfo:
    width: int | None = None
    height: int | None = None
    duration_s: float | None = None
    frame: Image.Image | None = None


def _find_atom(f, start: int, end: int, name: bytes) -> tuple[int, int] | None:
    """Return (payload_start, payload_end) of the first `name` atom in [start, end)."""
    pos = start
    while pos + 8 <= end:
        f.seek(pos)
        header = f.read(8)
        if len(header) < 8:
            return None
        size, kind = struct.unpack(">I4s", header)
        header_len = 8
        if size == 1:
            size = struct.unpack(">Q", f.read(8))[0]
            header_len = 16
        elif size == 0:
            size = end - pos
        if size < header_len:
            return None
        if kind == name:
            return pos + header_len, pos + size
        pos += size
    return None


def read_creation_time(path: Path) -> datetime | None:
    """Creation time from the `moov/mvhd` atom, as local naive datetime."""
    try:
        with open_source(path) as f:
            size = os.fstat(f.fileno()).st_size
            moov = _find_atom(f, 0, size, b"moov")
            if not moov:
                return None
            mvhd = _find_atom(f, moov[0], moov[1], b"mvhd")
            if not mvhd:
                return None
            f.seek(mvhd[0])
            version = f.read(4)[0]
            raw = f.read(8 if version == 1 else 4)
            seconds = int.from_bytes(raw, "big")
    except (OSError, struct.error, IndexError):
        return None
    if seconds <= _QT_EPOCH_OFFSET:
        return None
    utc = datetime.fromtimestamp(seconds - _QT_EPOCH_OFFSET, tz=timezone.utc)
    return utc.astimezone().replace(tzinfo=None)


def read_video(path: Path) -> VideoInfo | None:
    """Dimensions, duration and a frame ~1s in. None if OpenCV can't open it."""
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            return None
        info = VideoInfo()
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        if w and h:
            info.width, info.height = w, h
        if fps > 0 and frames > 0:
            info.duration_s = round(frames / fps, 2)

        seek_ms = min(1000.0, (info.duration_s or 0) * 500)
        cap.set(cv2.CAP_PROP_POS_MSEC, seek_ms)
        ok, frame = cap.read()
        if not ok:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = cap.read()
        if ok and frame is not None:
            info.frame = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            # Rotated phone videos: trust the decoded frame's shape
            info.height, info.width = frame.shape[:2]
        return info
    finally:
        cap.release()
