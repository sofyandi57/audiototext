"""Wires settings, storage, queue and the pluggable engines together."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .asr import AsrEngine, build_asr
from .config import Settings
from .db import Database, now
from .diarization import DiarizationEngine, build_diarization
from .intelligence import build_intelligence
from .jobs import JobQueue
from .pdf import TesseractOCR
from .storage import Storage
from .tts import TTSEngine, build_engines

log = logging.getLogger(__name__)


@dataclass
class Services:
    settings: Settings
    db: Database
    storage: Storage
    queue: JobQueue
    ocr: TesseractOCR | None
    tts: dict[str, TTSEngine]
    asr: AsrEngine
    diarization: DiarizationEngine
    intelligence: Any
    extra: dict = field(default_factory=dict)

    def tts_engine(self, name: str | None = None) -> TTSEngine:
        name = name or self.settings.tts_engine
        if name not in self.tts:
            raise KeyError(name)
        return self.tts[name]


def build_services(settings: Settings, **overrides) -> Services:
    settings.ensure_dirs()
    db = Database(settings.db_path)
    parts = dict(
        settings=settings,
        db=db,
        storage=Storage(settings.uploads_dir, settings.derived_dir),
        queue=JobQueue(db, settings.job_max_attempts),
        ocr=TesseractOCR(settings.ocr_languages, settings.ocr_dpi) if settings.ocr_enabled else None,
        tts=build_engines(settings),
        asr=build_asr(settings),
        diarization=build_diarization(settings),
        intelligence=build_intelligence(settings),
    )
    parts.update(overrides)
    return Services(**parts)


def delete_document(services: Services, doc_id: str) -> None:
    services.queue.cancel_for_target(doc_id)
    services.storage.delete_item(doc_id)
    services.db.execute("DELETE FROM documents WHERE id=?", (doc_id,))


def delete_meeting(services: Services, meeting_id: str) -> None:
    services.queue.cancel_for_target(meeting_id)
    services.storage.delete_item(meeting_id)
    services.db.execute("DELETE FROM meetings WHERE id=?", (meeting_id,))


def apply_retention(services: Services) -> dict:
    """Delete items (and their files) older than the retention window."""
    days = services.settings.retention_days
    if days <= 0:
        return {"documents": 0, "meetings": 0}
    cutoff = now() - days * 86400
    docs = services.db.all("SELECT id FROM documents WHERE created_at < ?", (cutoff,))
    meets = services.db.all("SELECT id FROM meetings WHERE created_at < ?", (cutoff,))
    for d in docs:
        delete_document(services, d["id"])
    for m in meets:
        delete_meeting(services, m["id"])
    services.db.execute(
        "DELETE FROM jobs WHERE created_at < ? AND status IN ('succeeded','failed','cancelled')",
        (cutoff,),
    )
    if docs or meets:
        log.info("retention removed %d documents, %d meetings", len(docs), len(meets))
    return {"documents": len(docs), "meetings": len(meets)}
