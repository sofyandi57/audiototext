"""Piper adapter (neural VITS voices, ONNX, CPU).

Status: implemented but NOT verified in this project's environment — voice
downloads (huggingface.co) were blocked, and we have not confirmed that an
Indonesian Piper voice with a suitable licence exists. Point
``MI_PIPER_MODEL_PATH`` at any local ``.onnx`` voice (with its ``.onnx.json``
next to it) and the ``piper`` CLI on PATH to enable it. Check the voice's own
licence/model card before distributing audio.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .base import EngineInfo, TTSEngine, TTSUnavailable


class PiperEngine(TTSEngine):
    name = "piper"
    max_chunk_chars = 1000

    def __init__(self, model_path: str = ""):
        self.binary = shutil.which("piper")
        self.model = Path(model_path) if model_path else None

    def info(self) -> EngineInfo:
        reason = None
        if not self.binary:
            reason = "Program 'piper' tidak ditemukan di PATH."
        elif not self.model or not self.model.is_file():
            reason = "MI_PIPER_MODEL_PATH belum menunjuk ke file suara .onnx lokal."
        elif not Path(str(self.model) + ".json").is_file():
            reason = "File konfigurasi suara (.onnx.json) tidak ditemukan."
        voices = [{"id": self.model.stem, "label": self.model.stem}] if self.model and not reason else []
        return EngineInfo(
            name=self.name, available=reason is None, reason=reason,
            license="Piper: MIT; lisensi suara bervariasi per model — periksa model card.",
            file_output=True, voices=voices,
            notes="Belum diverifikasi untuk Bahasa Indonesia di lingkungan pengujian proyek ini.",
        )

    def synthesize(self, text: str, out_wav: Path, voice: str | None = None,
                   rate_wpm: int | None = None) -> None:
        info = self.info()
        if not info.available:
            raise TTSUnavailable(info.reason or "Piper tidak tersedia.")
        args = [self.binary, "--model", str(self.model), "--output_file", str(out_wav)]
        if rate_wpm:
            # piper's length_scale: >1 slower. 160 wpm ~ 1.0
            args += ["--length_scale", f"{max(0.5, min(2.0, 160 / rate_wpm)):.2f}"]
        proc = subprocess.run(args, input=text, capture_output=True, text=True, timeout=600)
        if proc.returncode != 0 or not out_wav.exists():
            raise RuntimeError("Piper gagal menghasilkan audio.")
