"""Transkripsi file audio/video ke teks memakai OpenAI Whisper."""

import datetime
import os
import tempfile

import whisper

_MODEL_CACHE = {}


def load_model(model_size):
    """Load model Whisper (di-cache di memori supaya tidak load ulang tiap file)."""
    if model_size not in _MODEL_CACHE:
        _MODEL_CACHE[model_size] = whisper.load_model(model_size)
    return _MODEL_CACHE[model_size]


def _format_timestamp(seconds):
    total_ms = int(max(seconds, 0) * 1000)
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def segments_to_srt(segments):
    lines = []
    for i, seg in enumerate(segments, start=1):
        start = _format_timestamp(seg["start"])
        end = _format_timestamp(seg["end"])
        text = seg["text"].strip()
        lines.append(f"{i}\n{start} --> {end}\n{text}\n")
    return "\n".join(lines)


def transcribe_file(file_bytes, file_name, model_size="small", language=None, task="transcribe"):
    """Transkripsi satu file audio/video (bytes) dan kembalikan dict hasil:
    {"error", "text", "srt", "language"}.

    language=None -> Whisper mendeteksi bahasa otomatis.
    task="translate" -> hasil langsung diterjemahkan ke Bahasa Inggris (fitur bawaan Whisper).
    """
    suffix = os.path.splitext(file_name)[1] or ".audio"
    result = {"error": None, "text": "", "srt": "", "language": None}

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        model = load_model(model_size)
        whisper_result = model.transcribe(
            tmp_path,
            language=language,
            task=task,
            fp16=False,
            verbose=False,
        )
        result["text"] = whisper_result["text"].strip()
        result["srt"] = segments_to_srt(whisper_result["segments"])
        result["language"] = whisper_result.get("language")
    except Exception as exc:  # ditampilkan apa adanya ke user di UI
        result["error"] = str(exc)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

    return result
