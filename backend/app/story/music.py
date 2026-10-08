"""Slideshow music from a user-chosen folder. Read-only: files are only listed and streamed."""

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

AUDIO_TYPES = {
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".opus": "audio/ogg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
}


@dataclass
class Track:
    id: str
    title: str
    rel_path: str
    size: int

    def as_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "file": self.rel_path, "size": self.size}


def track_id(rel_path: str) -> str:
    return hashlib.sha1(rel_path.lower().encode()).hexdigest()[:16]


def nice_title(stem: str) -> str:
    title = stem.replace("_", " ").replace("-", " - ").strip()
    while "  " in title:
        title = title.replace("  ", " ")
    return title


def list_tracks(folder: Path) -> list[Track]:
    tracks = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = sorted((d for d in dirnames if not d.startswith(".")), key=str.lower)
        for name in sorted(filenames, key=str.lower):
            p = Path(dirpath) / name
            if p.suffix.lower() in AUDIO_TYPES and not name.startswith("."):
                rel = p.relative_to(folder).as_posix()
                tracks.append(Track(track_id(rel), nice_title(p.stem), rel, p.stat().st_size))
    return tracks
