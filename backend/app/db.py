"""SQLite persistence for the single-instance prototype.

WAL mode + busy timeout lets the API process and a separate worker process
share the same database file safely.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    page_count INTEGER,
    status TEXT NOT NULL,            -- uploaded | extracting | review | generating | ready | failed
    ocr_available INTEGER,
    cleaning_report TEXT,            -- JSON: what was removed/merged and why
    error TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_documents_sha ON documents(sha256);

CREATE TABLE IF NOT EXISTS doc_pages (
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_no INTEGER NOT NULL,        -- 1-based
    char_count INTEGER NOT NULL,
    text_source TEXT NOT NULL,       -- text | ocr | none
    needs_review INTEGER NOT NULL DEFAULT 0,
    review_reason TEXT,
    PRIMARY KEY (document_id, page_no)
);

CREATE TABLE IF NOT EXISTS sections (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    title TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 1,
    text TEXT NOT NULL,
    start_page INTEGER,
    end_page INTEGER,
    edited INTEGER NOT NULL DEFAULT 0,
    needs_review INTEGER NOT NULL DEFAULT 0,
    audio_status TEXT NOT NULL DEFAULT 'none',  -- none | done | failed
    audio_file TEXT,
    audio_duration REAL,
    audio_engine TEXT,
    audio_text_hash TEXT,           -- hash of text the audio was generated from
    audio_error TEXT
);
CREATE INDEX IF NOT EXISTS idx_sections_doc ON sections(document_id, idx);

CREATE TABLE IF NOT EXISTS meetings (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    title TEXT,
    duration REAL,
    status TEXT NOT NULL,            -- uploaded | converting | transcribing | analyzing | ready | failed
    language TEXT,
    asr_engine TEXT,
    asr_model TEXT,
    diarization TEXT,
    error TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_meetings_sha ON meetings(sha256);

CREATE TABLE IF NOT EXISTS meeting_chunks (
    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    start REAL NOT NULL,
    end REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',     -- pending | done | failed
    error TEXT,
    PRIMARY KEY (meeting_id, idx)
);

CREATE TABLE IF NOT EXISTS segments (
    id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    chunk_idx INTEGER NOT NULL,
    idx INTEGER NOT NULL,            -- global order within meeting
    start REAL NOT NULL,
    end REAL NOT NULL,
    text TEXT NOT NULL,
    original_text TEXT NOT NULL,
    speaker TEXT,
    confidence REAL,
    edited INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_segments_meeting ON segments(meeting_id, start);

CREATE TABLE IF NOT EXISTS insights (
    id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,              -- summary | decision | risk | question | action
    text TEXT NOT NULL,
    owner TEXT,
    owner_confirmed INTEGER NOT NULL DEFAULT 0,
    deadline TEXT,
    deadline_confirmed INTEGER NOT NULL DEFAULT 0,
    segment_ids TEXT NOT NULL,       -- JSON list, never empty
    start REAL NOT NULL,
    end REAL NOT NULL,
    engine TEXT NOT NULL,
    idx INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_insights_meeting ON insights(meeting_id, kind, idx);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,              -- pdf_extract | tts_generate | meeting_transcribe | meeting_analyze
    target_id TEXT NOT NULL,
    params TEXT NOT NULL DEFAULT '{}',
    idempotency_key TEXT NOT NULL,
    status TEXT NOT NULL,            -- queued | running | succeeded | failed | cancelled
    stage TEXT,
    progress REAL NOT NULL DEFAULT 0,
    error TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    started_at REAL,
    finished_at REAL,
    heartbeat_at REAL,
    worker_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_target ON jobs(target_id, created_at);
-- At most one active (queued/running) job per idempotency key.
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_active_key ON jobs(idempotency_key)
    WHERE status IN ('queued', 'running');
"""


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


def now() -> float:
    return time.time()


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """Immediate write transaction (serialises writers across processes)."""
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            else:
                conn.execute("COMMIT")

    def one(self, sql: str, args: tuple | list = ()) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(sql, args).fetchone()
            return dict(row) if row else None

    def all(self, sql: str, args: tuple | list = ()) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(sql, args).fetchall()]

    def execute(self, sql: str, args: tuple | list = ()) -> int:
        with self.connect() as conn:
            return conn.execute(sql, args).rowcount


def loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    return json.loads(value)
