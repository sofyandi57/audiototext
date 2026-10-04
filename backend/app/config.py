"""Application settings, loaded from environment variables (prefix ``MI_``).

All paths default to a ``data/`` directory that lives outside any public web
root. Uploaded files are only ever served through authenticated API routes.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MI_", env_file=".env", extra="ignore")

    # Storage
    data_dir: Path = REPO_DIR / "data"
    # Built frontend (Next.js static export). Served at "/" when present.
    frontend_dir: Path = REPO_DIR / "frontend" / "out"

    # Optional shared access token. When set, every /api route except
    # /api/health requires it (header "Authorization: Bearer ..." or cookie).
    access_token: str = ""

    # Upload limits
    max_pdf_mb: int = 50
    max_media_mb: int = 500
    max_pdf_pages: int = 1500
    max_media_minutes: int = 240

    # Retention: uploads and derived files older than this are deleted.
    # 0 disables automatic deletion.
    retention_days: int = 30

    # Worker
    run_worker_in_process: bool = True
    worker_poll_seconds: float = 1.0
    job_stale_seconds: int = 600  # running job without heartbeat -> requeued
    job_max_attempts: int = 3

    # PDF
    ocr_enabled: bool = True
    ocr_languages: str = "ind+eng"
    ocr_dpi: int = 300
    min_page_chars: int = 25  # below this a page is "low text"
    section_max_chars: int = 6000

    # TTS
    tts_engine: str = "espeak-ng"  # espeak-ng | piper
    tts_voice: str = "id"
    tts_rate_wpm: int = 160
    piper_model_path: str = ""  # path to a local .onnx voice

    # ASR
    asr_engine: str = "faster-whisper"
    whisper_model: str = "small"  # model name or local directory
    whisper_compute_type: str = "int8"
    whisper_local_files_only: bool = True  # never fetch at request time unless allowed
    whisper_download_root: str = ""
    asr_language: str = "id"
    asr_chunk_seconds: int = 300
    asr_initial_prompt: str = ""  # glossary of names/terms to bias decoding

    # Diarization
    diarization_engine: str = "none"

    # Meeting intelligence
    intelligence_engine: str = "rules"  # rules | ollama
    ollama_url: str = ""
    ollama_model: str = ""

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def derived_dir(self) -> Path:
        return self.data_dir / "derived"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.sqlite3"

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.uploads_dir, self.derived_dir):
            p.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
