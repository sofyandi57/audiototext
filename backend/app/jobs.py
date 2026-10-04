"""Persistent job queue backed by SQLite.

Design notes
- Job ids are stable: a user retry re-queues the same job row.
- At most one queued/running job exists per idempotency key (partial unique
  index), so double clicks and repeated API calls do not duplicate work.
- A worker claims a job atomically inside ``BEGIN IMMEDIATE``. While running
  it heartbeats; a job whose heartbeat goes stale (worker crashed / container
  restarted) is re-queued by ``recover_stale``.
- Handlers persist their own partial results (per section / per audio chunk),
  so a retried job resumes instead of restarting from zero.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass
from typing import Any, Callable

from .db import Database, new_id, now

log = logging.getLogger(__name__)

ACTIVE = ("queued", "running")
TERMINAL = ("succeeded", "failed", "cancelled")


class JobError(Exception):
    """Actionable, user-facing failure. ``retryable=False`` skips auto-retry."""

    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.message = message
        self.retryable = retryable


class JobCancelled(Exception):
    pass


def make_key(kind: str, target_id: str, params: dict[str, Any] | None) -> str:
    blob = json.dumps(params or {}, sort_keys=True)
    return f"{kind}:{target_id}:{hashlib.sha256(blob.encode()).hexdigest()[:16]}"


class JobQueue:
    def __init__(self, db: Database, max_attempts: int = 3):
        self.db = db
        self.max_attempts = max_attempts

    # -- creation -----------------------------------------------------------
    def enqueue(self, kind: str, target_id: str, params: dict[str, Any] | None = None) -> dict:
        """Create a job, or return the already-active job with the same key."""
        key = make_key(kind, target_id, params)
        existing = self.active_by_key(key)
        if existing:
            return existing
        job_id = new_id("job")
        t = now()
        try:
            self.db.execute(
                "INSERT INTO jobs (id, kind, target_id, params, idempotency_key, status, stage,"
                " max_attempts, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (job_id, kind, target_id, json.dumps(params or {}), key, "queued", "queued",
                 self.max_attempts, t, t),
            )
        except sqlite3.IntegrityError:
            existing = self.active_by_key(key)
            if existing:
                return existing
            raise
        return self.get(job_id)  # type: ignore[return-value]

    def active_by_key(self, key: str) -> dict | None:
        return self.db.one(
            "SELECT * FROM jobs WHERE idempotency_key=? AND status IN ('queued','running')", (key,)
        )

    # -- reads --------------------------------------------------------------
    def get(self, job_id: str) -> dict | None:
        return self.db.one("SELECT * FROM jobs WHERE id=?", (job_id,))

    def list(self, target_id: str | None = None, limit: int = 100) -> list[dict]:
        if target_id:
            return self.db.all(
                "SELECT * FROM jobs WHERE target_id=? ORDER BY created_at DESC LIMIT ?",
                (target_id, limit),
            )
        return self.db.all("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,))

    def latest_for(self, target_id: str) -> dict | None:
        rows = self.list(target_id, limit=1)
        return rows[0] if rows else None

    # -- worker side --------------------------------------------------------
    def claim(self, worker_id: str) -> dict | None:
        with self.db.tx() as conn:
            row = conn.execute(
                "SELECT id FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if not row:
                return None
            t = now()
            conn.execute(
                "UPDATE jobs SET status='running', attempts=attempts+1, started_at=?,"
                " heartbeat_at=?, updated_at=?, worker_id=?, stage='starting', error=NULL"
                " WHERE id=?",
                (t, t, t, worker_id, row["id"]),
            )
            job = conn.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone()
            return dict(job)

    def heartbeat(self, job_id: str, stage: str | None = None, progress: float | None = None) -> bool:
        """Update liveness/progress. Returns False if the job is no longer running."""
        sets, args = ["heartbeat_at=?", "updated_at=?"], [now(), now()]
        if stage is not None:
            sets.append("stage=?")
            args.append(stage)
        if progress is not None:
            sets.append("progress=?")
            args.append(max(0.0, min(1.0, progress)))
        args.append(job_id)
        n = self.db.execute(
            f"UPDATE jobs SET {', '.join(sets)} WHERE id=? AND status='running'", args
        )
        return n == 1

    def succeed(self, job_id: str) -> None:
        t = now()
        self.db.execute(
            "UPDATE jobs SET status='succeeded', stage='done', progress=1, finished_at=?,"
            " updated_at=?, error=NULL WHERE id=? AND status='running'",
            (t, t, job_id),
        )

    def fail(self, job_id: str, message: str, retryable: bool) -> str:
        """Record a failure. Returns the new status (queued for auto-retry, or failed)."""
        job = self.get(job_id)
        if not job or job["status"] != "running":
            return job["status"] if job else "missing"
        t = now()
        if retryable and job["attempts"] < job["max_attempts"]:
            self.db.execute(
                "UPDATE jobs SET status='queued', stage='waiting to retry', error=?, updated_at=?"
                " WHERE id=?",
                (message, t, job_id),
            )
            return "queued"
        self.db.execute(
            "UPDATE jobs SET status='failed', error=?, finished_at=?, updated_at=? WHERE id=?",
            (message, t, t, job_id),
        )
        return "failed"

    def recover_stale(self, stale_seconds: int) -> list[str]:
        """Re-queue running jobs whose worker stopped heartbeating."""
        cutoff = now() - stale_seconds
        stale = self.db.all(
            "SELECT * FROM jobs WHERE status='running' AND COALESCE(heartbeat_at, 0) < ?", (cutoff,)
        )
        recovered = []
        for job in stale:
            if job["attempts"] < job["max_attempts"]:
                n = self.db.execute(
                    "UPDATE jobs SET status='queued', stage='recovered after interruption',"
                    " updated_at=? WHERE id=? AND status='running'",
                    (now(), job["id"]),
                )
            else:
                n = self.db.execute(
                    "UPDATE jobs SET status='failed', error=?, finished_at=?, updated_at=?"
                    " WHERE id=? AND status='running'",
                    ("Job was interrupted too many times.", now(), now(), job["id"]),
                )
            if n:
                recovered.append(job["id"])
        return recovered

    # -- user actions -------------------------------------------------------
    def retry(self, job_id: str) -> dict:
        """Re-queue a failed/cancelled job (same id). Returns the active job."""
        job = self.get(job_id)
        if not job:
            raise KeyError(job_id)
        if job["status"] in ACTIVE:
            return job
        if job["status"] == "succeeded":
            raise JobError("Job already succeeded; start a new run instead.")
        try:
            self.db.execute(
                "UPDATE jobs SET status='queued', stage='queued', attempts=0, error=NULL,"
                " progress=0, finished_at=NULL, updated_at=? WHERE id=?",
                (now(), job_id),
            )
        except sqlite3.IntegrityError:
            other = self.active_by_key(job["idempotency_key"])
            if other:
                return other
            raise
        return self.get(job_id)  # type: ignore[return-value]

    def cancel(self, job_id: str) -> dict | None:
        self.db.execute(
            "UPDATE jobs SET status='cancelled', finished_at=?, updated_at=? WHERE id=?"
            " AND status IN ('queued','running')",
            (now(), now(), job_id),
        )
        return self.get(job_id)

    def cancel_for_target(self, target_id: str) -> None:
        self.db.execute(
            "UPDATE jobs SET status='cancelled', finished_at=?, updated_at=? WHERE target_id=?"
            " AND status IN ('queued','running')",
            (now(), now(), target_id),
        )


@dataclass
class JobContext:
    job: dict
    queue: JobQueue
    services: Any  # app.services.Services

    @property
    def params(self) -> dict:
        return json.loads(self.job.get("params") or "{}")

    def report(self, stage: str, progress: float | None = None) -> None:
        if not self.queue.heartbeat(self.job["id"], stage, progress):
            raise JobCancelled()


@dataclass
class Handler:
    run: Callable[[JobContext], None]
    on_failure: Callable[[JobContext, str], None] | None = None
