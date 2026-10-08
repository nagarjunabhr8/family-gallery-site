"""SQLAlchemy models. Phase 1: folders, media, scan jobs, settings."""

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


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text)  # JSON-encoded
