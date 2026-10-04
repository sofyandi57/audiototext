from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AsrSegment:
    start: float  # seconds, relative to the audio passed in
    end: float
    text: str
    confidence: float | None = None


@dataclass
class AsrInfo:
    name: str
    model: str
    available: bool
    reason: str | None
    supports_diarization: bool = False
    license: str = ""


class AsrUnavailable(Exception):
    pass


class AsrEngine(ABC):
    name = "base"

    @abstractmethod
    def info(self) -> AsrInfo: ...

    @abstractmethod
    def transcribe(self, wav: Path, language: str | None = None,
                   initial_prompt: str | None = None) -> list[AsrSegment]: ...
