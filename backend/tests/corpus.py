"""Synthetic test corpus. Everything is generated locally; no real documents
or recordings are used."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pymupdf as fitz

HEADER = "Laporan Teknis Proyek Nusantara"
FOOTER_TMPL = "Halaman {n} dari {total}"

CHAPTERS = [
    ("BAB I PENDAHULUAN", [
        "Proyek Nusantara bertujuan membangun sistem transkripsi rapat berbahasa Indonesia "
        "yang berjalan di CPU tanpa GPU. Tim memakai FastAPI dan SQLite untuk prototipe awal.",
        "Dokumen ini menjelaskan arsitektur, batasan, dan rencana pengujian sistem.",
    ]),
    ("BAB II METODOLOGI", [
        "Data uji dibuat secara sintetis agar tidak ada rekaman rapat rahasia yang diunggah "
        "ke layanan publik. Setiap kalimat memiliki transkrip acuan yang diperiksa manual.",
        "Akurasi diukur dengan Word Error Rate dan ketepatan istilah teknis seperti API, "
        "deployment, dan backend.",
    ]),
    ("BAB III HASIL", [
        "Hasil awal menunjukkan bahwa model kecil cukup untuk rapat dengan audio yang jernih.",
        "Pekerjaan lanjutan mencakup diarisasi pembicara dan evaluasi suara sintesis.",
    ]),
]


def _decorate(page: fitz.Page, n: int, total: int) -> None:
    page.insert_text((72, 40), HEADER, fontsize=9, fontname="helv")
    page.insert_text((250, 815), FOOTER_TMPL.format(n=n, total=total), fontsize=9, fontname="helv")


def _paragraphs(page: fitz.Page, y: float, paragraphs: list[str]) -> float:
    for para in paragraphs:
        rect = fitz.Rect(72, y, 523, y + 200)
        rc = page.insert_textbox(rect, para, fontsize=11, fontname="helv")
        used = 200 - rc if rc >= 0 else 200
        y += used + 14
    return y


def make_book_pdf(path: Path, with_outline: bool = False) -> Path:
    """Three chapters, one per page, with repeated header and page-number footer."""
    doc = fitz.open()
    total = len(CHAPTERS)
    toc = []
    for i, (title, paras) in enumerate(CHAPTERS, start=1):
        page = doc.new_page(width=595, height=842)
        _decorate(page, i, total)
        page.insert_text((72, 110), title, fontsize=18, fontname="hebo")
        _paragraphs(page, 135, paras)
        toc.append([1, title, i])
    if with_outline:
        doc.set_toc(toc)
    doc.save(path)
    doc.close()
    return path


def make_wrapped_pdf(path: Path) -> Path:
    """Lines broken mid-word with hyphens, plus Indonesian reduplication, and a
    paragraph that continues across a page break."""
    doc = fitz.open()
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((72, 100), "Catatan Teknis", fontsize=18, fontname="hebo")
    lines = [
        "Sistem ini mengguna-",
        "kan pemrosesan bertahap agar anak-",
        "anak dapat mendengarkan buku dengan",
    ]
    y = 140
    for ln in lines:
        p1.insert_text((72, y), ln, fontsize=11, fontname="helv")
        y += 14
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((72, 100), "nyaman di perangkat Android.", fontsize=11, fontname="helv")
    doc.save(path)
    doc.close()
    return path


def make_two_column_pdf(path: Path) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 80), "Judul Dua Kolom", fontsize=18, fontname="hebo")
    left = "Kolom kiri paragraf pertama. Kolom kiri paragraf kedua lanjut di bawah."
    right = "Kolom kanan dibaca setelah kolom kiri selesai dibaca."
    page.insert_textbox(fitz.Rect(72, 110, 280, 300), left, fontsize=11, fontname="helv")
    page.insert_textbox(fitz.Rect(315, 110, 523, 300), right, fontsize=11, fontname="helv")
    doc.save(path)
    doc.close()
    return path


def make_scanned_pdf(path: Path, text: str = "Ini halaman hasil pindaian untuk uji OCR.") -> Path:
    """A page whose content is only a raster image of text (no text layer)."""
    src = fitz.open()
    page = src.new_page(width=595, height=842)
    page.insert_textbox(fitz.Rect(72, 100, 523, 400), "Dokumen Pindaian\n\n" + text,
                        fontsize=16, fontname="helv")
    pix = page.get_pixmap(dpi=200)
    src.close()
    doc = fitz.open()
    out = doc.new_page(width=595, height=842)
    out.insert_image(out.rect, pixmap=pix)
    doc.save(path)
    doc.close()
    return path


def make_empty_pdf(path: Path) -> Path:
    doc = fitz.open()
    doc.new_page()
    doc.save(path)
    doc.close()
    return path


def make_malformed_pdf(path: Path) -> Path:
    path.write_bytes(b"%PDF-1.4\n1 0 obj << /Type /Catalog >>\nthis is not really a pdf\n")
    return path


# --- audio ---------------------------------------------------------------

def espeak_available() -> bool:
    return shutil.which("espeak-ng") is not None


def make_speech_wav(path: Path, text: str, voice: str = "id") -> Path:
    subprocess.run(["espeak-ng", "-v", voice, "-s", "150", "-w", str(path), text], check=True,
                   capture_output=True)
    return path


def make_tone(path: Path, seconds: float = 3.0, video: bool = False) -> Path:
    """Sine tone audio, or a tiny video with an audio track when ``video``."""
    if video:
        cmd = ["ffmpeg", "-y", "-loglevel", "error",
               "-f", "lavfi", "-i", f"color=c=black:s=160x120:d={seconds}",
               "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
               "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)]
    else:
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
               "-i", f"sine=frequency=440:duration={seconds}", str(path)]
    subprocess.run(cmd, check=True)
    return path
