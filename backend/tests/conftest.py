from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.asr.base import AsrEngine, AsrInfo, AsrSegment  # noqa: E402
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services import build_services  # noqa: E402
from app.worker import Worker  # noqa: E402


class FakeASR(AsrEngine):
    """Deterministic stand-in for faster-whisper (real weights are not
    downloadable in CI). Emits two segments per chunk, relative to the chunk."""

    name = "fake-asr"

    def __init__(self, fail_on_call: set[int] | None = None, available: bool = True):
        self.calls = 0
        self.fail_on_call = fail_on_call or set()
        self._available = available

    def info(self) -> AsrInfo:
        return AsrInfo(self.name, "fake", self._available,
                       None if self._available else "model tidak ada (uji)")

    def transcribe(self, wav, language=None, initial_prompt=None):
        self.calls += 1
        if self.calls in self.fail_on_call:
            raise RuntimeError("simulated crash")
        n = self.calls
        return [
            AsrSegment(0.5, 2.0, f"Kalimat pertama potongan {n}.", 0.9),
            AsrSegment(3.0, 4.5, f"Kalimat kedua potongan {n}.", 0.8),
        ]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        frontend_dir=tmp_path / "no-frontend",
        run_worker_in_process=False,
        retention_days=30,
        asr_chunk_seconds=10,
        _env_file=None,
    )


@pytest.fixture
def fake_asr() -> FakeASR:
    return FakeASR()


@pytest.fixture
def services(settings, fake_asr):
    return build_services(settings, asr=fake_asr)


@pytest.fixture
def client(services):
    from fastapi.testclient import TestClient

    app = create_app(services=services, start_worker=False)
    with TestClient(app) as c:
        yield c


def drain(services, max_jobs: int = 50) -> int:
    """Run queued jobs synchronously until the queue is empty."""
    worker = Worker(services, heartbeat_seconds=0.2)
    n = 0
    while n < max_jobs and worker.run_once():
        n += 1
    return n


requires_espeak = pytest.mark.skipif(shutil.which("espeak-ng") is None, reason="espeak-ng not installed")
requires_tesseract = pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")
requires_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
