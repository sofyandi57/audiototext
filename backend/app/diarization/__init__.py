"""Speaker diarization adapter.

No diarization model has been verified in this project (pyannote and similar
need model downloads that were unavailable during development), so the
default engine reports itself unavailable and speakers are assigned manually
in the UI. A real engine only needs to implement ``assign``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DiarizationInfo:
    name: str
    available: bool
    reason: str | None


class DiarizationEngine(ABC):
    name = "base"

    @abstractmethod
    def info(self) -> DiarizationInfo: ...

    @abstractmethod
    def assign(self, wav: Path, segments: list[tuple[float, float]]) -> list[str | None]:
        """Return one speaker label (or None) per (start, end) segment."""


class NoDiarization(DiarizationEngine):
    name = "none"

    def info(self) -> DiarizationInfo:
        return DiarizationInfo(
            self.name, False,
            "Diarisasi otomatis belum tersedia. Beri label pembicara secara manual di transkrip.",
        )

    def assign(self, wav: Path, segments: list[tuple[float, float]]) -> list[str | None]:
        return [None] * len(segments)


def build_diarization(settings) -> DiarizationEngine:
    return NoDiarization()
