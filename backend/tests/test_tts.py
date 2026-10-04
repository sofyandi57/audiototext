from __future__ import annotations

import subprocess
import wave

import pytest

from app.audio import ffmpeg
from app.tts import TTSUnavailable
from app.tts.base import EngineInfo, TTSEngine
from app.tts.espeak import EspeakEngine
from app.tts.pipeline import chunk_text, normalize, synthesize_section
from app.tts.piper import PiperEngine

from .conftest import requires_espeak, requires_ffmpeg


class ToneEngine(TTSEngine):
    """Adapter-conformance stand-in: 0.05 s of tone per character."""

    name = "tone"
    max_chunk_chars = 50

    def __init__(self):
        self.inputs: list[str] = []

    def info(self):
        return EngineInfo(self.name, True, None, "test", True)

    def synthesize(self, text, out_wav, voice=None, rate_wpm=None):
        self.inputs.append(text)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        f"sine=frequency=300:duration={len(text) * 0.05:.2f}", str(out_wav)], check=True)


def test_chunking_respects_limit_and_words():
    text = ("Kalimat pertama cukup panjang untuk diuji. " * 10).strip() + "\n\nParagraf dua."
    chunks = chunk_text(text, 100)
    assert all(len(c) <= 100 for c in chunks)
    assert " ".join(chunks).split() == text.split()
    assert chunks[-1] == "Paragraf dua."


def test_chunking_hard_splits_long_sentence_at_spaces():
    text = "kata " * 100
    chunks = chunk_text(text, 42)
    assert all(len(c) <= 42 for c in chunks)
    assert all(not c.startswith(" ") and "kat " not in c for c in chunks)


def test_normalize_expands_common_abbreviations():
    assert normalize("buku, pena, dll.") == "buku, pena, dan lain-lain"
    assert normalize("harga Rp 5000") == "harga rupiah 5000"


@requires_ffmpeg
def test_pipeline_with_any_engine_produces_valid_mp3(tmp_path):
    eng = ToneEngine()
    out = tmp_path / "x.mp3"
    duration = synthesize_section(eng, "Halo dunia. " * 12, out)
    assert len(eng.inputs) > 1  # chunked
    assert out.exists() and out.read_bytes()[:3] in (b"ID3", b"\xff\xfb", b"\xff\xf3")
    info = ffmpeg.probe(out)
    assert info.has_audio and abs(info.duration - duration) < 0.01
    assert duration == pytest.approx(sum(len(t) for t in eng.inputs) * 0.05, abs=0.6)


def test_pipeline_rejects_empty_text(tmp_path):
    with pytest.raises(ValueError):
        synthesize_section(ToneEngine(), "   \n\n ", tmp_path / "x.mp3")


@requires_espeak
def test_espeak_indonesian_voice_available():
    info = EspeakEngine().info()
    assert info.available and info.file_output
    assert any(v["id"] == "id" for v in info.voices)


@requires_espeak
@requires_ffmpeg
def test_espeak_generates_audio_with_plausible_duration(tmp_path):
    text = "Selamat datang di buku audio. Bab satu membahas pengantar sistem transkripsi."
    out = tmp_path / "e.mp3"
    duration = synthesize_section(EspeakEngine(), text, out, rate_wpm=160)
    words = len(text.split())
    # 160 wpm => ~4.1 s for 11 words; allow generous bounds for pauses.
    assert words / 160 * 60 * 0.6 < duration < words / 160 * 60 * 2.0
    wav = tmp_path / "e.wav"
    EspeakEngine().synthesize(text, wav)
    with wave.open(str(wav)) as w:
        assert w.getnchannels() == 1 and w.getnframes() > 0


@requires_espeak
def test_espeak_rate_changes_duration(tmp_path):
    text = "Kecepatan bicara dapat diatur oleh pengguna aplikasi."
    slow = synthesize_section(EspeakEngine(), text, tmp_path / "s.mp3", rate_wpm=100)
    fast = synthesize_section(EspeakEngine(), text, tmp_path / "f.mp3", rate_wpm=250)
    assert slow > fast * 1.5


@requires_espeak
def test_espeak_unknown_voice_falls_back_to_indonesian(tmp_path):
    EspeakEngine().synthesize("tes suara", tmp_path / "v.wav", voice="; rm -rf /")
    assert (tmp_path / "v.wav").stat().st_size > 100


def test_piper_reports_unavailable_without_model(tmp_path):
    eng = PiperEngine(str(tmp_path / "missing.onnx"))
    info = eng.info()
    assert info.available is False and info.reason
    with pytest.raises(TTSUnavailable):
        eng.synthesize("halo", tmp_path / "x.wav")
