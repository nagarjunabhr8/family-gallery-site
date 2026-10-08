"""Read-only guarantees for photo sources.

Every file the app writes must go through this module. Writes are refused
unless the target resolves to a path inside the app data folder. Originals are
only ever opened with `open_source`, which is read-only binary.
"""

import os
from pathlib import Path
from typing import BinaryIO


class UnsafeWriteError(PermissionError):
    """Raised when something tries to write outside the data folder."""


_data_dir: Path | None = None


def set_data_dir(path: str | Path) -> Path:
    global _data_dir
    _data_dir = Path(path).resolve()
    _data_dir.mkdir(parents=True, exist_ok=True)
    return _data_dir


def data_dir() -> Path:
    if _data_dir is None:
        raise RuntimeError("Data folder is not configured")
    return _data_dir


def check_writable(path: str | Path) -> Path:
    """Return the resolved path if it is inside the data folder, else raise."""
    target = Path(path).resolve()
    root = data_dir()
    if not target.is_relative_to(root):
        raise UnsafeWriteError(f"Refusing to write outside the data folder: {target}")
    return target


def safe_mkdir(path: str | Path) -> Path:
    target = check_writable(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def safe_write_bytes(path: str | Path, data: bytes) -> Path:
    """Atomically write bytes to a file inside the data folder."""
    target = check_writable(path)
    safe_mkdir(target.parent)
    tmp = check_writable(target.with_name(target.name + ".tmp"))
    tmp.write_bytes(data)
    os.replace(tmp, target)
    return target


def safe_unlink(path: str | Path) -> None:
    check_writable(path).unlink(missing_ok=True)


def open_source(path: str | Path) -> BinaryIO:
    """Open an original photo/video. Always read-only, binary."""
    return open(path, "rb")


def is_inside(child: str | Path, parent: str | Path) -> bool:
    return Path(child).resolve().is_relative_to(Path(parent).resolve())
