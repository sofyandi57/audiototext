"""Optional local LLM engine via an Ollama-compatible HTTP endpoint.

Free and local, but NOT verified in this project (no model could be
downloaded in the development environment). Disabled unless
``MI_INTELLIGENCE_ENGINE=ollama`` and ``MI_OLLAMA_URL``/``MI_OLLAMA_MODEL``
are set. Its output passes through the same provenance validator as the
rule engine: items that do not cite real segment ids are dropped.
"""

from __future__ import annotations

import json

import httpx

from .provenance import KINDS, Item

PROMPT = """Anda menganalisis transkrip rapat berbahasa Indonesia.
Setiap baris diawali ID segmen dalam kurung siku. Kembalikan HANYA JSON:
{{"items": [{{"kind": "summary|decision|risk|question|action", "text": "...",
  "segment_ids": ["..."], "owner": null, "deadline": null}}]}}
Aturan: jangan mengarang. Setiap item WAJIB mengutip segment_ids yang ada.
Isi owner/deadline hanya jika disebut eksplisit di segmen yang dikutip; jika tidak, null.

TRANSKRIP:
{transcript}
"""


class OllamaEngine:
    name = "ollama"

    def __init__(self, url: str, model: str, timeout: float = 600):
        self.url = url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def info(self) -> dict:
        if not self.url or not self.model:
            return {"name": self.name, "available": False,
                    "reason": "MI_OLLAMA_URL dan MI_OLLAMA_MODEL belum diatur."}
        try:
            r = httpx.get(f"{self.url}/api/tags", timeout=3)
            names = {m.get("name") for m in r.json().get("models", [])}
            ok = self.model in names or f"{self.model}:latest" in names
            return {"name": self.name, "available": ok,
                    "reason": None if ok else f"Model '{self.model}' tidak ada di server Ollama."}
        except Exception:
            return {"name": self.name, "available": False, "reason": "Server Ollama tidak dapat dihubungi."}

    def _call(self, prompt: str) -> str:
        r = httpx.post(f"{self.url}/api/generate", timeout=self.timeout, json={
            "model": self.model, "prompt": prompt, "stream": False, "format": "json",
            "options": {"temperature": 0},
        })
        r.raise_for_status()
        return r.json().get("response", "")

    def analyze(self, segments: list[dict]) -> list[Item]:
        transcript = "\n".join(
            f"[{s['id']}] {(s.get('speaker') or 'Pembicara')}: {s['text']}" for s in segments
        )
        raw = self._call(PROMPT.format(transcript=transcript))
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        items = []
        for d in data.get("items", []) if isinstance(data, dict) else []:
            if not isinstance(d, dict) or d.get("kind") not in KINDS:
                continue
            ids = d.get("segment_ids") or []
            if not isinstance(ids, list):
                continue
            items.append(Item(
                kind=d["kind"], text=str(d.get("text") or "").strip(),
                segment_ids=[str(i) for i in ids],
                owner=(str(d["owner"]).strip() or None) if d.get("owner") else None,
                deadline=(str(d["deadline"]).strip() or None) if d.get("deadline") else None,
            ))
        return items
