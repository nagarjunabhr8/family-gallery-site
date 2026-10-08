"""User-tunable settings stored as JSON in the settings table."""

import json
from typing import Any

from sqlalchemy.orm import Session

from .models import Setting

DEFAULTS: dict[str, Any] = {
    # pHash Hamming distance (0..64) at or below which two photos are near-duplicates
    "near_dup_threshold": 8,
    # Looser distance for photos taken in the same minute (bursts)
    "burst_threshold": 20,
    "burst_enabled": True,
    # Events: a gap longer than this (hours) starts a new event
    "event_gap_hours": 6,
    # ...as does a jump of more than this many km between geotagged photos
    "event_gps_km": 30,
    # Smaller clusters are gathered into a monthly "Moments" event
    "event_min_photos": 3,
    # CLIP scene tag confidence (0..1) needed to tag a photo
    "tag_threshold": 0.35,
}


def get_all(s: Session) -> dict[str, Any]:
    values = dict(DEFAULTS)
    for row in s.query(Setting).filter(Setting.key.in_(DEFAULTS)).all():
        values[row.key] = json.loads(row.value)
    return values


def update(s: Session, changes: dict[str, Any]) -> dict[str, Any]:
    for key, value in changes.items():
        if key not in DEFAULTS:
            raise KeyError(key)
        row = s.get(Setting, key)
        if row is None:
            s.add(Setting(key=key, value=json.dumps(value)))
        else:
            row.value = json.dumps(value)
    s.commit()
    return get_all(s)
