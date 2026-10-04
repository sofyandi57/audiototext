"""Background worker. Runs inside the API process by default, or standalone:

    python -m app.worker

Processes one job at a time on purpose: ASR/TTS are CPU-bound, and running
several in parallel on a small free-tier machine only makes each one slower
and risks running out of memory.
"""

from __future__ import annotations

import logging
import os
import signal
import socket
import threading
import time

from .config import get_settings
from .jobs import Handler, JobCancelled, JobContext, JobError
from .pipelines import HANDLERS
from .services import Services, apply_retention, build_services

log = logging.getLogger(__name__)

INTERNAL_ERROR = "Terjadi kesalahan internal saat memproses ({stage}). Kode referensi: {job_id}."


class Worker:
    def __init__(self, services: Services, handlers: dict[str, Handler] | None = None,
                 heartbeat_seconds: float = 10.0):
        self.services = services
        self.handlers = handlers or HANDLERS
        self.heartbeat_seconds = heartbeat_seconds
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}:{id(self) % 10000}"
        self._last_recover = 0.0
        self._last_retention = 0.0

    def maintenance(self, force: bool = False) -> None:
        t = time.time()
        if force or t - self._last_recover >= 60:
            self._last_recover = t
            recovered = self.services.queue.recover_stale(self.services.settings.job_stale_seconds)
            if recovered:
                log.warning("re-queued stale jobs: %s", recovered)
        if force or t - self._last_retention >= 3600:
            self._last_retention = t
            apply_retention(self.services)

    def run_once(self) -> bool:
        q = self.services.queue
        job = q.claim(self.worker_id)
        if not job:
            return False
        handler = self.handlers.get(job["kind"])
        ctx = JobContext(job=job, queue=q, services=self.services)
        if handler is None:
            q.fail(job["id"], f"Jenis pekerjaan tidak dikenal: {job['kind']}", retryable=False)
            return True

        stop = threading.Event()

        def beat() -> None:
            while not stop.wait(self.heartbeat_seconds):
                q.heartbeat(job["id"])

        hb = threading.Thread(target=beat, daemon=True)
        hb.start()
        try:
            handler.run(ctx)
        except JobCancelled:
            log.info("job %s cancelled", job["id"])
        except JobError as exc:
            status = q.fail(job["id"], exc.message, exc.retryable)
            if status == "failed" and handler.on_failure:
                handler.on_failure(ctx, exc.message)
        except Exception:
            log.exception("job %s crashed", job["id"])
            current = q.get(job["id"]) or job
            msg = INTERNAL_ERROR.format(stage=current.get("stage") or "-", job_id=job["id"])
            status = q.fail(job["id"], msg, retryable=True)
            if status == "failed" and handler.on_failure:
                handler.on_failure(ctx, msg)
        else:
            q.succeed(job["id"])
        finally:
            stop.set()
            hb.join(timeout=1)
        return True

    def run_forever(self, stop_event: threading.Event) -> None:
        log.info("worker %s started", self.worker_id)
        self.maintenance(force=True)
        while not stop_event.is_set():
            try:
                self.maintenance()
                if not self.run_once():
                    stop_event.wait(self.services.settings.worker_poll_seconds)
            except Exception:  # never let the loop die
                log.exception("worker loop error")
                stop_event.wait(5)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    services = build_services(get_settings())
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    Worker(services).run_forever(stop)


if __name__ == "__main__":
    main()
