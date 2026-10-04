"""Engine-independent synthesis: normalise, chunk, synthesise, encode MP3."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from ..audio import ffmpeg
from .base import TTSEngine

_ABBREV = {
    r"\bdll\.": "dan lain-lain",
    r"\bdsb\.": "dan sebagainya",
    r"\btsb\.": "tersebut",
    r"\byg\b": "yang",
    r"\bdgn\b": "dengan",
    r"\bspt\b": "seperti",
    r"\bno\.\s*(?=\d)": "nomor ",
    r"\bhlm\.\s*(?=\d)": "halaman ",
    r"\bRp\.?\s*(?=\d)": "rupiah ",
}


def normalize(text: str) -> str:
    t = text.replace("­", "")
    for pat, rep in _ABBREV.items():
        t = re.sub(pat, rep, t, flags=re.IGNORECASE)
    t = re.sub(r"[ \t]+", " ", t)
    return t.strip()


def chunk_text(text: str, max_chars: int) -> list[str]:
    """Split at paragraph, then sentence, then word boundaries; never mid-word."""
    chunks: list[str] = []
    for para in [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]:
        if len(para) <= max_chars:
            chunks.append(para)
            continue
        buf = ""
        for sent in re.split(r"(?<=[.!?;:])\s+", para):
            while len(sent) > max_chars:
                cut = sent.rfind(" ", 0, max_chars)
                cut = cut if cut > 0 else max_chars
                if buf:
                    chunks.append(buf)
                    buf = ""
                chunks.append(sent[:cut].strip())
                sent = sent[cut:].strip()
            if buf and len(buf) + 1 + len(sent) > max_chars:
                chunks.append(buf)
                buf = sent
            else:
                buf = f"{buf} {sent}".strip()
        if buf:
            chunks.append(buf)
    return [c for c in chunks if c]


def synthesize_section(engine: TTSEngine, text: str, out_mp3: Path, voice: str | None = None,
                       rate_wpm: int | None = None) -> float:
    """Synthesise ``text`` into ``out_mp3``. Returns the validated duration (s)."""
    chunks = chunk_text(normalize(text), engine.max_chunk_chars)
    if not chunks:
        raise ValueError("Bagian ini tidak berisi teks untuk dibacakan.")
    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        for i, chunk in enumerate(chunks):
            wav = Path(tmp) / f"part{i:04d}.wav"
            engine.synthesize(chunk, wav, voice=voice, rate_wpm=rate_wpm)
            parts.append(wav)
        ffmpeg.concat_to_mp3(parts, out_mp3)
    info = ffmpeg.probe(out_mp3)
    if not info.has_audio or info.duration <= 0:
        out_mp3.unlink(missing_ok=True)
        raise RuntimeError("File audio yang dihasilkan tidak valid.")
    return info.duration
