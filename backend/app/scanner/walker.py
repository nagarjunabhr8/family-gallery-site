"""Recursive discovery of supported media files. Only lists; never writes."""

import os
from collections.abc import Iterator
from pathlib import Path

from ..config import SKIP_DIR_NAMES, SUPPORTED_EXTS
from ..safety import data_dir


def iter_media_files(root: Path) -> Iterator[Path]:
    """Yield supported files under `root`, sorted, skipping hidden/system dirs and the data folder."""
    app_data = data_dir()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        here = Path(dirpath)
        dirnames[:] = sorted(
            d
            for d in dirnames
            if not d.startswith(".") and d not in SKIP_DIR_NAMES and (here / d).resolve() != app_data
        )
        for name in sorted(filenames):
            if name.startswith("._"):  # macOS resource-fork files
                continue
            if Path(name).suffix.lower() in SUPPORTED_EXTS:
                yield here / name
