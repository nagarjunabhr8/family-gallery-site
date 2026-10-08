"""SQLAlchemy models: library (P1), duplicates/quality (P2), people (P3), events/occasions (P4)."""

from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Index, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now()


class SourceFolder(Base):
    __tablename__ = "source_folders"

    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str] = mapped_column(String, unique=True)
    enabled: Mapped[bool] = mapped_column(default=True)
    added_at: Mapped[datetime] = mapped_column(default=_now)
    last_scanned_at: Mapped[datetime | None] = mapped_column(default=None)


class Media(Base):
    __tablename__ = "media"
    __table_args__ = (
        UniqueConstraint("folder_id", "rel_path"),
        Index("ix_media_taken_at", "taken_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    folder_id: Mapped[int] = mapped_column(
        ForeignKey("source_folders.id", ondelete="CASCADE"), index=True
    )
    rel_path: Mapped[str] = mapped_column(String)  # posix-style, relative to folder
    filename: Mapped[str] = mapped_column(String)
    ext: Mapped[str] = mapped_column(String(8))
    kind: Mapped[str] = mapped_column(String(8))  # photo | video

    # Change detection for incremental re-scan
    size: Mapped[int]
    mtime_ns: Mapped[int]
    sha256: Mapped[str | None] = mapped_column(String(64), index=True, default=None)

    width: Mapped[int | None] = mapped_column(default=None)  # display orientation
    height: Mapped[int | None] = mapped_column(default=None)
    duration_s: Mapped[float | None] = mapped_column(default=None)
    orientation: Mapped[int | None] = mapped_column(default=None)

    taken_at: Mapped[datetime]
    date_source: Mapped[str] = mapped_column(String(16))  # exif | video_meta | filename | mtime
    date_confidence: Mapped[str] = mapped_column(String(8))  # high | medium | low

    gps_lat: Mapped[float | None] = mapped_column(default=None)
    gps_lon: Mapped[float | None] = mapped_column(default=None)
    camera: Mapped[str | None] = mapped_column(String, default=None)

    # Phase 2: perceptual hash (64-bit, hex) and the user's manual best-shot choice
    phash: Mapped[str | None] = mapped_column(String(16), default=None)
    pinned_best: Mapped[bool] = mapped_column(default=False)

    # Phase 5: extra rotation chosen in the viewer (0/90/180/270). Display only; the file is never touched.
    user_rotation: Mapped[int] = mapped_column(default=0)

    has_thumb: Mapped[bool] = mapped_column(default=False)
    missing: Mapped[bool] = mapped_column(default=False)  # file no longer found on disk
    error: Mapped[str | None] = mapped_column(Text, default=None)
    scanned_at: Mapped[datetime] = mapped_column(default=_now)


class ScanJob(Base):
    __tablename__ = "scan_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), default="scan")  # scan | analyze
    # queued | running | done | cancelled | failed | interrupted
    status: Mapped[str] = mapped_column(String(16), default="queued")
    folder_id: Mapped[int | None] = mapped_column(default=None)  # None = all folders
    created_at: Mapped[datetime] = mapped_column(default=_now)
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    total: Mapped[int] = mapped_column(default=0)
    processed: Mapped[int] = mapped_column(default=0)
    added: Mapped[int] = mapped_column(default=0)
    updated: Mapped[int] = mapped_column(default=0)
    unchanged: Mapped[int] = mapped_column(default=0)
    missing: Mapped[int] = mapped_column(default=0)
    errors: Mapped[int] = mapped_column(default=0)
    message: Mapped[str | None] = mapped_column(Text, default=None)


class Quality(Base):
    """Per-photo quality analysis. Component scores are 0..1; total is 0..100."""

    __tablename__ = "quality"

    media_id: Mapped[int] = mapped_column(ForeignKey("media.id", ondelete="CASCADE"), primary_key=True)
    version: Mapped[int]
    media_mtime_ns: Mapped[int]  # analysis is stale when the file changes
    sharpness_raw: Mapped[float]  # Laplacian variance at 1024px
    sharpness: Mapped[float]
    exposure: Mapped[float]
    resolution: Mapped[float]
    faces: Mapped[int] = mapped_column(default=0)
    face_score: Mapped[float | None] = mapped_column(default=None)  # None = no judgeable faces
    eyes_open: Mapped[float | None] = mapped_column(default=None)  # fraction of faces with eyes open
    aesthetic_raw: Mapped[float | None] = mapped_column(default=None)  # LAION scale ~1..10
    aesthetic: Mapped[float | None] = mapped_column(default=None)  # None = model not installed
    total: Mapped[float]
    models_used: Mapped[str] = mapped_column(String, default="")  # re-analyze when this changes
    analyzed_at: Mapped[datetime] = mapped_column(default=_now)


class ClipEmbedding(Base):
    """L2-normalised CLIP image embedding (float32 bytes). Reused for scene tags in Phase 4."""

    __tablename__ = "clip_embeddings"

    media_id: Mapped[int] = mapped_column(ForeignKey("media.id", ondelete="CASCADE"), primary_key=True)
    model: Mapped[str] = mapped_column(String(32))
    vector: Mapped[bytes] = mapped_column(LargeBinary)


class DupGroup(Base):
    """A set of photos that are copies or near-copies. Rebuilt on every regroup."""

    __tablename__ = "dup_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(8))  # exact | near | burst
    best_media_id: Mapped[int] = mapped_column(ForeignKey("media.id", ondelete="CASCADE"))
    size: Mapped[int]
    taken_at: Mapped[datetime]  # of the best photo, for sorting


class DupMember(Base):
    __tablename__ = "dup_members"

    media_id: Mapped[int] = mapped_column(ForeignKey("media.id", ondelete="CASCADE"), primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("dup_groups.id", ondelete="CASCADE"), index=True)
    distance: Mapped[int] = mapped_column(default=0)  # pHash distance to the best photo


class Person(Base):
    __tablename__ = "persons"
    # ids are never reused, so "not this person" corrections can't point at a new stranger
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String, default=None)  # None = unnamed cluster
    birth_date: Mapped[date | None] = mapped_column(Date, default=None)
    hidden: Mapped[bool] = mapped_column(default=False)  # e.g. strangers in the background
    cover_face_id: Mapped[int | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class Face(Base):
    """One detected face. Box/landmarks are normalised (0..1) to the upright photo."""

    __tablename__ = "faces"

    id: Mapped[int] = mapped_column(primary_key=True)
    media_id: Mapped[int] = mapped_column(ForeignKey("media.id", ondelete="CASCADE"), index=True)
    x: Mapped[float]
    y: Mapped[float]
    w: Mapped[float]
    h: Mapped[float]
    landmarks: Mapped[str] = mapped_column(Text)  # JSON [[x,y] x5], normalised
    det_score: Mapped[float]
    size_px: Mapped[int]  # face width in the 1600px analysis image
    quality: Mapped[float]  # 0..1, how usable for recognition
    eyes_open: Mapped[bool | None] = mapped_column(default=None)
    embedding: Mapped[bytes] = mapped_column(LargeBinary)  # 512 float32, L2-normalised (ArcFace)
    person_id: Mapped[int | None] = mapped_column(
        ForeignKey("persons.id", ondelete="SET NULL"), index=True, default=None
    )
    assigned_by: Mapped[str] = mapped_column(String(8), default="auto")  # auto | user
    not_person_ids: Mapped[str] = mapped_column(Text, default="[]")  # JSON: people this face is NOT


class MediaTag(Base):
    """CLIP zero-shot scene tag (birthday, temple, ...). Recomputed on every analysis."""

    __tablename__ = "media_tags"

    media_id: Mapped[int] = mapped_column(ForeignKey("media.id", ondelete="CASCADE"), primary_key=True)
    tag: Mapped[str] = mapped_column(String(32), primary_key=True, index=True)
    score: Mapped[float]


class Event(Base):
    """A group of media from one occasion/outing.

    kind: auto (time-gap grouping) | moments (small clusters of one month) | custom (user-made).
    Locked events were edited by the user: they keep their photos across rebuilds
    and absorb new photos that fall inside their time window.
    """

    __tablename__ = "events"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(8), default="auto")
    title: Mapped[str | None] = mapped_column(String, default=None)  # None = generated
    description: Mapped[str | None] = mapped_column(Text, default=None)
    start_at: Mapped[datetime]
    end_at: Mapped[datetime]
    locked: Mapped[bool] = mapped_column(default=False)
    hero_media_id: Mapped[int | None] = mapped_column(default=None)
    hero_by_user: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class EventMedia(Base):
    __tablename__ = "event_media"

    media_id: Mapped[int] = mapped_column(ForeignKey("media.id", ondelete="CASCADE"), primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    assigned_by: Mapped[str] = mapped_column(String(8), default="auto")  # auto | user


class Occasion(Base):
    """A family date that repeats every year: birthday, anniversary, other."""

    __tablename__ = "occasions"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))  # birthday | anniversary | other
    name: Mapped[str] = mapped_column(String)
    month: Mapped[int]
    day: Mapped[int]
    year: Mapped[int | None] = mapped_column(default=None)  # first year (birth/wedding), for "3rd"
    person_id: Mapped[int | None] = mapped_column(
        ForeignKey("persons.id", ondelete="SET NULL"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(default=_now)


class FestivalDate(Base):
    """When a festival fell in a given year. Seeded from a built-in table; user-editable."""

    __tablename__ = "festival_dates"
    __table_args__ = (UniqueConstraint("festival", "year"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    festival: Mapped[str] = mapped_column(String(32))
    year: Mapped[int]
    date: Mapped[date] = mapped_column(Date)  # the main day
    start: Mapped[date] = mapped_column(Date)  # e.g. Bhogi for Sankranti
    end: Mapped[date] = mapped_column(Date)  # e.g. Kanuma for Sankranti
    user_edited: Mapped[bool] = mapped_column(default=False)


class StoryStage(Base):
    """A chapter of the life story ("Childhood", "College", "Marriage"…). Ends where the next begins."""

    __tablename__ = "story_stages"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    start: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(16), default="custom")  # childhood|school|college|career|marriage|kids|custom
    suggested: Mapped[bool] = mapped_column(default=False)  # made by "Suggest", not edited since
    created_at: Mapped[datetime] = mapped_column(default=_now)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text)  # JSON-encoded
