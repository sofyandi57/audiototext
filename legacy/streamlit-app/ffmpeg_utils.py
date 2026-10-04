"""Deteksi lokasi ffmpeg di komputer ini (dibutuhkan Whisper untuk membaca file
audio/video apa pun, karena Whisper mendekode audio lewat ffmpeg sebagai subprocess)."""

import os
import shutil
import sys


def _app_dir():
    """Folder tempat .exe berada (atau folder skrip ini saat dijalankan sebagai .py)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def find_ffmpeg_dir():
    """Cari folder yang berisi ffmpeg.exe, urutan prioritas:
    1. Folder "ffmpeg-portable" di sebelah .exe/app (dibundel bareng, tidak perlu install apa pun).
    2. PATH.
    3. Lokasi instalasi umum di Windows (kalau user sudah install ffmpeg sendiri).

    Mengembalikan folder-nya (bukan path ke ffmpeg.exe) karena Whisper memanggil
    perintah "ffmpeg" langsung, jadi folder ini perlu ditambahkan ke PATH.
    """
    portable = os.path.join(_app_dir(), "ffmpeg-portable", "ffmpeg.exe")
    if os.path.isfile(portable):
        return os.path.dirname(portable)

    found = shutil.which("ffmpeg")
    if found:
        return os.path.dirname(found)

    default_paths = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\ffmpeg\bin\ffmpeg.exe"),
        os.path.expandvars(r"%ProgramFiles%\ffmpeg\bin\ffmpeg.exe"),
    ]
    for p in default_paths:
        if os.path.isfile(p):
            return os.path.dirname(p)
    return None


def ensure_ffmpeg_on_path():
    """Pastikan folder ffmpeg ada di PATH proses ini, supaya Whisper bisa menemukannya.
    Mengembalikan folder ffmpeg yang ditemukan, atau None kalau tidak ada."""
    ffmpeg_dir = find_ffmpeg_dir()
    if ffmpeg_dir and ffmpeg_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
    return ffmpeg_dir
