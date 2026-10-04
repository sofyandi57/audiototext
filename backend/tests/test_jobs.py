from __future__ import annotations

import threading

from app.db import now
from app.jobs import Handler, JobError
from app.worker import Worker


def test_enqueue_is_idempotent_while_active(services):
    q = services.queue
    a = q.enqueue("pdf_extract", "doc_x", {"a": 1})
    b = q.enqueue("pdf_extract", "doc_x", {"a": 1})
    c = q.enqueue("pdf_extract", "doc_x", {"a": 2})
    assert a["id"] == b["id"] and a["id"] != c["id"]


def test_concurrent_enqueue_creates_one_job(services):
    ids, q = [], services.queue

    def go():
        ids.append(q.enqueue("tts_generate", "doc_y", {})["id"])

    threads = [threading.Thread(target=go) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(set(ids)) == 1


def test_claim_is_exclusive(services):
    q = services.queue
    q.enqueue("k", "t1")
    got = []
    threads = [threading.Thread(target=lambda: got.append(q.claim("w"))) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sum(1 for g in got if g) == 1


def test_crash_is_retried_then_fails_with_on_failure(services):
    calls, failures = [], []

    def boom(ctx):
        calls.append(1)
        raise RuntimeError("secret /etc/path detail")

    handlers = {"k": Handler(boom, lambda ctx, msg: failures.append(msg))}
    job = services.queue.enqueue("k", "t1")
    w = Worker(services, handlers, heartbeat_seconds=0.1)
    while w.run_once():
        pass
    final = services.queue.get(job["id"])
    assert final["status"] == "failed"
    assert len(calls) == services.settings.job_max_attempts
    assert failures and "/etc/path" not in failures[0]  # no internals leaked
    assert job["id"] in final["error"]


def test_user_error_is_not_auto_retried(services):
    calls = []

    def bad(ctx):
        calls.append(1)
        raise JobError("PDF rusak")

    services.queue.enqueue("k", "t1")
    w = Worker(services, {"k": Handler(bad)}, heartbeat_seconds=0.1)
    while w.run_once():
        pass
    assert len(calls) == 1


def test_manual_retry_keeps_job_id_and_resets(services):
    attempts = []

    def flaky(ctx):
        attempts.append(1)
        if len(attempts) == 1:
            raise JobError("sementara gagal")

    job = services.queue.enqueue("k", "t1")
    w = Worker(services, {"k": Handler(flaky)}, heartbeat_seconds=0.1)
    w.run_once()
    assert services.queue.get(job["id"])["status"] == "failed"
    again = services.queue.retry(job["id"])
    assert again["id"] == job["id"] and again["status"] == "queued" and again["error"] is None
    w.run_once()
    assert services.queue.get(job["id"])["status"] == "succeeded"


def test_stale_running_job_is_recovered(services):
    q = services.queue
    job = q.enqueue("k", "t1")
    q.claim("dead-worker")
    services.db.execute("UPDATE jobs SET heartbeat_at=? WHERE id=?", (now() - 9999, job["id"]))
    assert q.recover_stale(600) == [job["id"]]
    assert q.get(job["id"])["status"] == "queued"
    done = []
    Worker(services, {"k": Handler(lambda ctx: done.append(1))}).run_once()
    assert done and q.get(job["id"])["status"] == "succeeded"


def test_cancel_stops_running_job_at_next_report(services):
    q = services.queue
    job = q.enqueue("k", "t1")
    seen = []

    def long(ctx):
        ctx.report("step 1", 0.1)
        q.cancel(job["id"])
        ctx.report("step 2", 0.5)  # raises JobCancelled
        seen.append("should not reach")

    Worker(services, {"k": Handler(long)}).run_once()
    assert q.get(job["id"])["status"] == "cancelled" and not seen


def test_progress_and_stage_are_persisted(services):
    q = services.queue
    job = q.enqueue("k", "t1")
    snapshot = {}

    def h(ctx):
        ctx.report("halaman 3/10", 0.3)
        snapshot.update(q.get(job["id"]))

    Worker(services, {"k": Handler(h)}).run_once()
    assert snapshot["stage"] == "halaman 3/10" and snapshot["progress"] == 0.3
