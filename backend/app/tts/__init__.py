from __future__ import annotations

from .base import EngineInfo, TTSEngine, TTSUnavailable
from .espeak import EspeakEngine
from .piper import PiperEngine


def build_engines(settings) -> dict[str, TTSEngine]:
    return {
        "espeak-ng": EspeakEngine(settings.tts_voice, settings.tts_rate_wpm),
        "piper": PiperEngine(settings.piper_model_path),
    }


__all__ = ["EngineInfo", "TTSEngine", "TTSUnavailable", "build_engines"]
