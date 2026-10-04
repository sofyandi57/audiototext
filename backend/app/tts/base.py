"""Common TTS adapter interface.

An engine turns plain text into a WAV file. Chunking, concatenation and MP3
encoding are handled by ``pipeline.synthesize_section`` so every engine gets
bounded inputs and identical output handling.

Browser speech synthesis is intentionally NOT an engine here: it runs in the
listener's browser, cannot produce a downloadable file, and is exposed only
as a preview in the frontend.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


class TTSUnavailable(Exception):
    pass


@dataclass
class EngineInfo:
    name: str
    available: bool
    reason: str | None
    license: str
    file_output: bool
    voices: list[dict] = field(default_factory=list)
    notes: str = ""


class TTSEngine(ABC):
    name: str = "base"
    max_chunk_chars: int = 1000

    @abstractmethod
    def info(self) -> EngineInfo: ...

    def available(self) -> bool:
        return self.info().available

    @abstractmethod
    def synthesize(self, text: str, out_wav: Path, voice: str | None = None,
                   rate_wpm: int | None = None) -> None:
        """Write ``text`` as speech to ``out_wav``. Raise on failure."""
