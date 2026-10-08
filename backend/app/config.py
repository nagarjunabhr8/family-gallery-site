"""Paths and constants. All generated data lives under the data folder."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

HOST = "127.0.0.1"
PORT = 8765

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".webp"}
VIDEO_EXTS = {".mp4", ".mov"}
SUPPORTED_EXTS = PHOTO_EXTS | VIDEO_EXTS

THUMB_MAX_EDGE = 480

# Directory names never descended into while scanning
SKIP_DIR_NAMES = {"$RECYCLE.BIN", "System Volume Information", "@eaDir", "node_modules"}


def default_data_dir() -> Path:
    """`FM_DATA_DIR` env var, else `family-memories/data/`."""
    return Path(os.environ.get("FM_DATA_DIR") or PROJECT_ROOT / "data").resolve()
