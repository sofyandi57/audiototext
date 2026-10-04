"""faster-whisper (CTranslate2) adapter — CPU, int8.

Model weights are NOT bundled. By default (``MI_WHISPER_LOCAL_FILES_ONLY=true``)
the adapter only uses models already on disk, so a request never blocks on a
multi-hundred-MB download. Pre-download once with
``python -m app.cli download-asr-model small`` on a machine with internet
access, or set ``MI_WHISPER_MODEL`` to a local CTranslate2 model directory.
"""

from __future__ import annotations

import logging
import math
import threading
from pathlib import Path

from .base import AsrEngine, AsrInfo, AsrSegment, AsrUnavailable

log = logging.getLogger(__name__)


class FasterWhisperEngine(AsrEngine):
    name = "faster-whisper"

    def __init__(self, model: str = "small", compute_type: str = "int8",
                 local_files_only: bool = True, download_root: str = "", beam_size: int = 5):
        self.model_name = model
        self.compute_type = compute_type
        self.local_files_only = local_files_only
        self.download_root = download_root or None
        self.beam_size = beam_size
        self._model = None
        self._lock = threading.Lock()
        self._resolved: str | None = None
        self._reason: str | None = None
        self._checked = False

    def _resolve(self) -> None:
        if self._checked:
            return
        self._checked = True
        try:
            from faster_whisper.utils import download_model
        except ImportError:
            self._reason = "Paket faster-whisper belum terpasang (pip install faster-whisper)."
            return
        local = Path(self.model_name)
        if local.is_dir():
            if (local / "model.bin").is_file():
                self._resolved = str(local)
            else:
                self._reason = f"Folder model '{local}' tidak berisi model.bin."
            return
        try:
            self._resolved = download_model(
                self.model_name, local_files_only=self.local_files_only,
                cache_dir=self.download_root,
            )
        except Exception as exc:  # network/cache errors vary by version
            log.info("faster-whisper model unavailable: %s", exc)
            self._reason = (
                f"Model Whisper '{self.model_name}' belum ada di server. Unduh sekali dengan "
                f"'python -m app.cli download-asr-model {self.model_name}' saat ada internet, "
                "atau set MI_WHISPER_MODEL ke folder model lokal."
            )

    def info(self) -> AsrInfo:
        self._resolve()
        return AsrInfo(
            name=self.name, model=self.model_name, available=self._resolved is not None,
            reason=self._reason, supports_diarization=False,
            license="faster-whisper: MIT; bobot Whisper: MIT",
        )

    def _load(self):
        self._resolve()
        if not self._resolved:
            raise AsrUnavailable(self._reason or "Model ASR tidak tersedia.")
        with self._lock:
            if self._model is None:
                from faster_whisper import WhisperModel
                self._model = WhisperModel(self._resolved, device="cpu",
                                           compute_type=self.compute_type)
        return self._model

    def transcribe(self, wav: Path, language: str | None = None,
                   initial_prompt: str | None = None) -> list[AsrSegment]:
        model = self._load()
        segments, _info = model.transcribe(
            str(wav), language=language or None, beam_size=self.beam_size,
            vad_filter=True, condition_on_previous_text=False,
            initial_prompt=initial_prompt or None,
        )
        out = []
        for s in segments:
            text = s.text.strip()
            if not text:
                continue
            conf = math.exp(s.avg_logprob) if s.avg_logprob is not None else None
            out.append(AsrSegment(float(s.start), float(s.end), text, conf))
        return out
