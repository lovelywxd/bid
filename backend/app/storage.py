import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from app.settings import Settings


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


class Storage:
    def __init__(self, settings: Settings):
        self.settings = settings
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.blobs = settings.data_dir / "objects"
        self.blobs.mkdir(exist_ok=True)
        self.engine = create_engine(settings.database_url, pool_pre_ping=True)
        if self.engine.dialect.name == "sqlite":
            @event.listens_for(self.engine, "connect")
            def pragmas(conn, _):
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=10000")

    @contextmanager
    def tx(self):
        # Single local worker and serialized writers. PostgreSQL advisory lock also
        # protects cross-process claims and global single-generation admission.
        with Session(self.engine, expire_on_commit=False) as session:
            if self.engine.dialect.name == "sqlite":
                session.execute(text("BEGIN IMMEDIATE"))
            else:
                session.begin()
                session.execute(text("SELECT pg_advisory_xact_lock(734620261112)"))
            try:
                yield session
                session.commit()
            except BaseException:
                session.rollback()
                raise

    def put(self, payload: dict) -> str:
        raw = canonical(payload)
        h = hashlib.sha256(raw).hexdigest()
        target = self.blobs / h
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest() != h:
                raise RuntimeError("BLOB_CORRUPTED")
            return h
        fd, path = tempfile.mkstemp(prefix=".pending-", dir=self.blobs)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(path, target)
        finally:
            Path(path).unlink(missing_ok=True)
        return h

    def verify(self, h: str) -> bool:
        target = self.blobs / h
        return target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == h
