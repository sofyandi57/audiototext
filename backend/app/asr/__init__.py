from __future__ import annotations

from .base import AsrEngine, AsrInfo, AsrSegment, AsrUnavailable
from .faster_whisper import FasterWhisperEngine


def build_asr(settings) -> AsrEngine:
    return FasterWhisperEngine(
        model=settings.whisper_model,
        compute_type=settings.whisper_compute_type,
        local_files_only=settings.whisper_local_files_only,
        download_root=settings.whisper_download_root,
    )


__all__ = ["AsrEngine", "AsrInfo", "AsrSegment", "AsrUnavailable", "build_asr"]
