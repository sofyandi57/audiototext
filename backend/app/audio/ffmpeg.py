"""Thin FFmpeg/ffprobe wrappers. All calls use argument lists (no shell)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class MediaError(Exception):
    """User-facing media problem (unreadable file, no audio stream...)."""


@dataclass
class MediaInfo:
    duration: float
    has_audio: bool
    has_video: bool
    format_name: str


def available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _run(cmd: list[str], timeout: int = 3600) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise MediaError("FFmpeg tidak terpasang di server.") from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaError("Pemrosesan audio melebihi batas waktu.") from exc
    return proc


def probe(path: Path) -> MediaInfo:
    proc = _run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format",
                 "-show_streams", str(path)], timeout=120)
    if proc.returncode != 0:
        raise MediaError("File tidak dapat dibaca sebagai audio/video.")
    data = json.loads(proc.stdout or "{}")
    streams = data.get("streams", [])
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    has_video = any(
        s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")
        for s in streams
    )
    duration = float(data.get("format", {}).get("duration") or 0)
    if not duration:
        for s in streams:
            if s.get("codec_type") == "audio" and s.get("duration"):
                duration = float(s["duration"])
    return MediaInfo(duration, has_audio, has_video, data.get("format", {}).get("format_name", ""))


def to_wav16k(src: Path, dst: Path) -> None:
    """Standard internal format: 16 kHz, mono, 16-bit PCM WAV."""
    proc = _run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-i", str(src), "-vn",
                 "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dst)])
    if proc.returncode != 0 or not dst.exists():
        raise MediaError("Gagal mengonversi audio ke format standar.")


def cut(src: Path, dst: Path, start: float, end: float) -> None:
    proc = _run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-ss", f"{start:.3f}",
                 "-to", f"{end:.3f}", "-i", str(src), "-c", "copy", str(dst)])
    if proc.returncode != 0:
        raise MediaError("Gagal memotong audio.")


def plan_chunks(duration: float, chunk_seconds: float) -> list[tuple[float, float]]:
    if duration <= 0:
        return []
    chunks, t = [], 0.0
    while t < duration - 0.05:
        end = min(duration, t + chunk_seconds)
        # avoid a tiny trailing chunk
        if duration - end < 5:
            end = duration
        chunks.append((round(t, 3), round(end, 3)))
        t = end
    return chunks


def concat_to_mp3(parts: list[Path], dst: Path, bitrate: str = "64k") -> None:
    if not parts:
        raise MediaError("Tidak ada audio untuk digabung.")
    listfile = dst.with_suffix(".txt")
    listfile.write_text("".join(f"file '{p.resolve()}'\n" for p in parts))
    tmp = dst.with_suffix(".part.mp3")
    try:
        proc = _run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                     "-i", str(listfile), "-ac", "1", "-c:a", "libmp3lame", "-b:a", bitrate, str(tmp)])
        if proc.returncode != 0:
            raise MediaError("Gagal membuat file MP3.")
        tmp.replace(dst)
    finally:
        listfile.unlink(missing_ok=True)
        tmp.unlink(missing_ok=True)


def concat_copy(parts: list[Path], dst: Path) -> None:
    """Concatenate same-codec files without re-encoding (for full-book export)."""
    listfile = dst.with_suffix(".txt")
    listfile.write_text("".join(f"file '{p.resolve()}'\n" for p in parts))
    tmp = dst.with_suffix(".part" + dst.suffix)
    try:
        proc = _run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                     "-i", str(listfile), "-c", "copy", str(tmp)])
        if proc.returncode != 0:
            raise MediaError("Gagal menggabungkan audio.")
        tmp.replace(dst)
    finally:
        listfile.unlink(missing_ok=True)
        tmp.unlink(missing_ok=True)


def detect_silences(path: Path, noise_db: int = -35, min_dur: float = 0.4) -> list[tuple[float, float]]:
    proc = _run(["ffmpeg", "-nostdin", "-hide_banner", "-i", str(path), "-af",
                 f"silencedetect=noise={noise_db}dB:d={min_dur}", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", proc.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", proc.stderr)]
    return list(zip(starts, ends))


def snap_chunks(chunks: list[tuple[float, float]], silences: list[tuple[float, float]],
                window: float = 20.0) -> list[tuple[float, float]]:
    """Move chunk boundaries to the nearest silence so words are not cut in half."""
    if len(chunks) < 2 or not silences:
        return chunks
    mids = [(a + b) / 2 for a, b in silences]
    bounds = [c[1] for c in chunks[:-1]]
    snapped = []
    prev = chunks[0][0]
    for b in bounds:
        near = [m for m in mids if abs(m - b) <= window and m > prev + 1]
        nb = min(near, key=lambda m: abs(m - b)) if near else b
        snapped.append(round(nb, 3))
        prev = nb
    edges = [chunks[0][0], *snapped, chunks[-1][1]]
    return [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]


def to_playback_mp3(src: Path, dst: Path) -> None:
    """Small mono MP3 that every mobile browser can play (source may be video/WMA)."""
    tmp = dst.with_suffix(".part.mp3")
    proc = _run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-i", str(src), "-vn", "-ac", "1",
                 "-c:a", "libmp3lame", "-b:a", "48k", str(tmp)])
    if proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise MediaError("Gagal membuat audio untuk diputar.")
    tmp.replace(dst)
