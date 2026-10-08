"""SQLite engine and session factory. The database file lives in the data folder."""

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from . import safety
from .models import Base

engine: Engine | None = None
SessionLocal = sessionmaker(expire_on_commit=False)


def init_db(data_dir: Path) -> Engine:
    global engine
    if engine is not None:
        engine.dispose()
    db_path = safety.check_writable(Path(data_dir) / "library.db")
    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

    Base.metadata.create_all(engine)
    _add_missing_columns(engine)
    SessionLocal.configure(bind=engine)
    return engine


def _add_missing_columns(engine: Engine) -> None:
    """Tiny forward-only migration: add columns that newer models define."""
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table.name})")}
            for col in table.columns:
                if col.name in existing:
                    continue
                ddl = f"ALTER TABLE {table.name} ADD COLUMN {col.name} {col.type.compile(engine.dialect)}"
                default = col.default.arg if col.default is not None and not callable(col.default.arg) else None
                if default is not None:
                    ddl += f" NOT NULL DEFAULT {int(default) if isinstance(default, bool) else repr(default)}"
                conn.exec_driver_sql(ddl)


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    with SessionLocal() as session:
        yield session
