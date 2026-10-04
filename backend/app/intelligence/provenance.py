"""Provenance guard shared by every intelligence engine.

Rules (applied to rule-based and model-generated items alike):
- every item must cite at least one existing transcript segment;
- start/end timestamps come from the cited segments, never from the engine;
- an owner is kept only if it literally appears in the cited text, or is the
  (human-labelled) speaker of a cited segment that says "saya/aku akan";
- a deadline is kept only if the phrase literally appears in the cited text;
- otherwise owner/deadline are cleared and marked unconfirmed.
Items that fail the first rule are rejected, not "repaired".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

KINDS = ("summary", "decision", "risk", "question", "action")


@dataclass
class Item:
    kind: str
    text: str
    segment_ids: list[str]
    owner: str | None = None
    deadline: str | None = None
    owner_confirmed: bool = False
    deadline_confirmed: bool = False
    start: float = 0.0
    end: float = 0.0


@dataclass
class ValidationResult:
    items: list[Item] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)


_SELF = re.compile(r"\b(saya|aku|gue|gw)\s+(akan|yang|siap|bisa)\b", re.I)


def _contains(haystack: str, needle: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(needle.strip().lower()) + r"(?!\w)", haystack.lower()) is not None


def validate(items: list[Item], segments: dict[str, dict]) -> ValidationResult:
    result = ValidationResult()
    for it in items:
        if it.kind not in KINDS:
            result.rejected.append({"text": it.text, "reason": f"unknown kind {it.kind!r}"})
            continue
        ids = [s for s in dict.fromkeys(it.segment_ids) if s in segments]
        if not ids or not it.text.strip():
            result.rejected.append({"text": it.text, "reason": "no valid transcript reference"})
            continue
        cited = [segments[s] for s in ids]
        cited_text = " ".join(c["text"] for c in cited)
        it.segment_ids = ids
        it.start = min(c["start"] for c in cited)
        it.end = max(c["end"] for c in cited)

        if it.owner:
            speakers = {(c.get("speaker") or "").lower() for c in cited if _SELF.search(c["text"])}
            if _contains(cited_text, it.owner) or it.owner.lower() in speakers:
                it.owner_confirmed = True
            else:
                it.owner, it.owner_confirmed = None, False
        else:
            it.owner_confirmed = False

        if it.deadline and _contains(cited_text, it.deadline):
            it.deadline_confirmed = True
        else:
            it.deadline, it.deadline_confirmed = None, False

        if it.kind != "action":
            it.owner = it.deadline = None
            it.owner_confirmed = it.deadline_confirmed = False
        result.items.append(it)
    return result
