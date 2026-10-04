"""eSpeak NG adapter: tiny, CPU-only, has an Indonesian voice ("id").

Quality is robotic but intelligible; it is the only Indonesian engine verified
in this project's test environment. Licence: GPL-3.0-or-later (engine). We
invoke it as a separate program, we do not link against it.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

from .base import EngineInfo, TTSEngine, TTSUnavailable


@lru_cache
def _voices(binary: str) -> list[dict]:
    try:
        out = subprocess.run([binary, "--voices=id"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return []
    voices = []
    for line in out.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 5 and parts[1] == "id":
            ident = parts[4]
            # mbrola voices need the separate mbrola binary + voice data
            if ident.startswith("mb/") and not shutil.which("mbrola"):
                continue
            voices.append({"id": "id" if ident == "poz/id" else ident.split("/")[-1],
                           "label": parts[3]})
    return voices


class EspeakEngine(TTSEngine):
    name = "espeak-ng"
    max_chunk_chars = 1500

    def __init__(self, default_voice: str = "id", default_rate: int = 160):
        self.binary = shutil.which("espeak-ng") or shutil.which("espeak")
        self.default_voice = default_voice
        self.default_rate = default_rate

    def info(self) -> EngineInfo:
        voices = _voices(self.binary) if self.binary else []
        ok = bool(self.binary and voices)
        return EngineInfo(
            name=self.name,
            available=ok,
            reason=None if ok else "espeak-ng atau suara Indonesia ('id') tidak terpasang.",
            license="GPL-3.0-or-later (engine dijalankan sebagai program terpisah)",
            file_output=True,
            voices=voices,
            notes="Suara sintetis formant: jelas tetapi terdengar robotik.",
        )

    def synthesize(self, text: str, out_wav: Path, voice: str | None = None,
                   rate_wpm: int | None = None) -> None:
        if not self.binary:
            raise TTSUnavailable("espeak-ng tidak terpasang.")
        voice = voice or self.default_voice
        allowed = {v["id"] for v in _voices(self.binary)}
        if voice not in allowed:
            voice = self.default_voice
        rate = max(80, min(400, int(rate_wpm or self.default_rate)))
        with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as f:
            f.write(text)
            txt = Path(f.name)
        try:
            proc = subprocess.run(
                [self.binary, "-v", voice, "-s", str(rate), "-w", str(out_wav), "-f", str(txt)],
                capture_output=True, text=True, timeout=600,
            )
        finally:
            txt.unlink(missing_ok=True)
        if proc.returncode != 0 or not out_wav.exists() or out_wav.stat().st_size < 100:
            raise RuntimeError("espeak-ng gagal menghasilkan audio.")
