from __future__ import annotations

from . import rules
from .ollama import OllamaEngine
from .provenance import Item, ValidationResult, validate


class RulesEngine:
    name = "rules"

    def info(self) -> dict:
        return {"name": self.name, "available": True, "reason": None,
                "notes": "Berbasis aturan: mengutip kalimat asli, tidak membuat kalimat baru."}

    def analyze(self, segments: list[dict]) -> list[Item]:
        return rules.analyze(segments)


def build_intelligence(settings):
    if settings.intelligence_engine == "ollama":
        return OllamaEngine(settings.ollama_url, settings.ollama_model)
    return RulesEngine()


def run_analysis(engine, segments: list[dict]) -> ValidationResult:
    items = engine.analyze(segments)
    return validate(items, {s["id"]: s for s in segments})


__all__ = ["Item", "RulesEngine", "OllamaEngine", "build_intelligence", "run_analysis", "validate"]
