"""Reproducible evaluation on the synthetic corpus.

    cd backend && python scripts/evaluate.py [--out ../eval-output]

Each benchmark runs in a fresh subprocess so wall time and peak RSS are
measured per task. Benchmarks whose engine is unavailable are reported as
SKIPPED with the reason — never as passed.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Synthetic Indonesian meeting lines with names, numbers, acronyms and
# Indonesian-English technical terms. The reference is the text itself.
ASR_REFERENCE = [
    "Selamat pagi semua, rapat evaluasi proyek Nusantara kita mulai sekarang.",
    "Bu Rina sudah menyiapkan laporan anggaran sebesar dua ratus lima puluh juta rupiah.",
    "Tim backend sepakat memakai FastAPI dan SQLite untuk prototipe pertama.",
    "Pak Budi, tolong siapkan dokumentasi API paling lambat hari Jumat.",
    "Risikonya server gratis tidak kuat untuk deployment model yang besar.",
    "Kita perlu menguji latency dan word error rate di CPU tanpa GPU.",
    "Sari akan memperbarui dashboard monitoring minggu depan.",
    "Apakah diarisasi pembicara masuk ke rilis versi satu?",
]
ASR_TERMS = ["Rina", "Budi", "Sari", "Nusantara", "FastAPI", "SQLite", "API", "backend", "deployment",
             "dashboard", "CPU", "GPU", "latency", "dua ratus lima puluh juta"]

TTS_SAMPLES = [
    "Bab satu. Pendahuluan.",
    "Pada tahun 2024, anggaran proyek mencapai Rp 1.500.000 dan diselesaikan dalam 3 bulan.",
    "Sistem ini memakai API berbasis FastAPI, lalu hasilnya diekspor ke format MP3.",
    "Anak-anak dapat mendengarkan buku audio ini di ponsel Android tanpa koneksi internet.",
]


def _measure(mode: str, *args: str) -> dict:
    """Run one benchmark in a child process; collect its JSON output + peak RSS."""
    t0 = time.perf_counter()
    proc = subprocess.run([sys.executable, __file__, "--bench", mode, *args], capture_output=True, text=True,
                          cwd=ROOT, timeout=3600)
    wall = time.perf_counter() - t0
    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:
        result = {"status": "ERROR", "stderr": proc.stderr[-2000:]}
    result["wall_seconds"] = round(wall, 2)
    return result


# ---------------------------------------------------------------- benches ---

def bench_pdf_reference() -> dict:
    from app.evaluation import token_recall
    from app.pdf import process_pdf
    from tests import corpus

    with tempfile.TemporaryDirectory() as tmp:
        doc = process_pdf(corpus.make_book_pdf(Path(tmp) / "b.pdf"), ocr=None)
    extracted = " ".join(s.text for s in doc.sections)
    reference = " ".join(" ".join(p) for _, p in corpus.CHAPTERS)
    leaked = corpus.HEADER in extracted or "dari 3" in extracted
    return {
        "status": "MEASURED",
        "body_token_recall": round(token_recall(reference, extracted), 4),
        "chapter_titles_correct_order": [s.title for s in doc.sections] == [c[0] for c in corpus.CHAPTERS],
        "header_footer_leaked_into_text": leaked,
        "removed_lines": doc.report["summary"],
    }


def bench_ocr() -> dict:
    from app.evaluation import cer
    from app.pdf import TesseractOCR, process_pdf
    from tests import corpus

    ocr = TesseractOCR("ind+eng")
    if not ocr.available():
        return {"status": "SKIPPED", "reason": "tesseract/ind data not installed"}
    text = ("Laporan ini disusun oleh tim Nusantara pada tanggal 12 Maret 2025. "
            "Anggaran operasional sebesar Rp 750.000 per bulan telah disetujui.")
    with tempfile.TemporaryDirectory() as tmp:
        t0 = time.perf_counter()
        doc = process_pdf(corpus.make_scanned_pdf(Path(tmp) / "s.pdf", text), ocr=ocr)
        secs = time.perf_counter() - t0
    out = " ".join(s.text for s in doc.sections).replace("Dokumen Pindaian", "").strip()
    return {"status": "MEASURED", "cer": round(cer(text, out), 4), "seconds_per_page": round(secs, 2),
            "ocr_text": out[:300]}


def bench_pdf_large(pages: str = "300") -> dict:
    import pymupdf

    from app.pdf import process_pdf
    from tests import corpus

    n = int(pages)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "large.pdf"
        doc = pymupdf.open()
        para = " ".join(p for _, ps in corpus.CHAPTERS for p in ps)
        for i in range(n):
            page = doc.new_page()
            page.insert_text((72, 40), corpus.HEADER, fontsize=9)
            if i % 10 == 0:
                page.insert_text((72, 100), f"BAB {i // 10 + 1} UJI", fontsize=18, fontname="hebo")
            page.insert_textbox(pymupdf.Rect(72, 130, 523, 760), (para + " ") * 3, fontsize=10)
            page.insert_text((280, 815), str(i + 1), fontsize=9)
        doc.save(path)
        doc.close()
        t0 = time.perf_counter()
        result = process_pdf(path, ocr=None)
        secs = time.perf_counter() - t0
    return {"status": "MEASURED", "pages": n, "seconds": round(secs, 2),
            "pages_per_second": round(n / secs, 1), "sections": len(result.sections),
            "chapters_detected": sum(1 for s in result.sections if "(bagian" not in s.title)}


def bench_tts() -> dict:
    from app.tts import EspeakEngine
    from app.tts.pipeline import synthesize_section

    eng = EspeakEngine()
    if not eng.info().available:
        return {"status": "SKIPPED", "reason": eng.info().reason}
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, text in enumerate(TTS_SAMPLES):
            t0 = time.perf_counter()
            dur = synthesize_section(eng, text, Path(tmp) / f"{i}.mp3", rate_wpm=160)
            secs = time.perf_counter() - t0
            words = len(text.split())
            rows.append({"text": text, "audio_seconds": round(dur, 2), "synth_seconds": round(secs, 3),
                         "real_time_factor": round(secs / dur, 3), "effective_wpm": round(words / dur * 60)})
        long_text = " ".join(TTS_SAMPLES) * 25  # ~ 1 chapter
        t0 = time.perf_counter()
        dur = synthesize_section(eng, long_text, Path(tmp) / "long.mp3")
        secs = time.perf_counter() - t0
    return {"status": "MEASURED", "engine": "espeak-ng (id)", "samples": rows,
            "chapter": {"chars": len(long_text), "audio_seconds": round(dur, 1), "synth_seconds": round(secs, 2),
                        "real_time_factor": round(secs / dur, 4)},
            "pronunciation_naturalness": "NOT MEASURED automatically: needs a human listening test "
                                         "(see docs/EVALUATION.md template)."}


def bench_asr(model: str = "") -> dict:
    from app.asr import FasterWhisperEngine
    from app.audio import ffmpeg
    from app.evaluation import cer, term_accuracy, wer
    from tests import corpus

    eng = FasterWhisperEngine(model or os.environ.get("MI_WHISPER_MODEL", "small"))
    info = eng.info()
    if not info.available:
        return {"status": "SKIPPED", "reason": info.reason}
    if not corpus.espeak_available():
        return {"status": "SKIPPED", "reason": "espeak-ng needed to synthesise the test audio"}
    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        for i, line in enumerate(ASR_REFERENCE):
            parts.append(corpus.make_speech_wav(Path(tmp) / f"{i}.wav", line))
        wav = Path(tmp) / "all.wav"
        ffmpeg.concat_copy(parts, wav)
        t0 = time.perf_counter()
        segs = eng.transcribe(wav, language="id")
        secs = time.perf_counter() - t0
        dur = ffmpeg.probe(wav).duration
    hyp = " ".join(s.text for s in segs)
    ref = " ".join(ASR_REFERENCE)
    return {"status": "MEASURED", "model": info.model, "audio": "espeak-ng synthetic voice (NOT real speech)",
            **wer(ref, hyp), "cer": round(cer(ref, hyp), 4), "terms": term_accuracy(ASR_TERMS, hyp),
            "audio_seconds": round(dur, 1), "transcribe_seconds": round(secs, 1),
            "real_time_factor": round(secs / dur, 3), "hypothesis": hyp}


def bench_concurrency(workers: str = "2") -> dict:
    """N worker processes share one SQLite DB; every job must run exactly once."""
    from app.config import Settings
    from app.db import new_id, now
    from app.services import build_services

    n_workers, n_docs = int(workers), 6
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "MI_DATA_DIR": tmp, "MI_WORKER_POLL_SECONDS": "0.2", "MI_RETENTION_DAYS": "0"}
        s = build_services(Settings(data_dir=Path(tmp), _env_file=None))
        text = " ".join(TTS_SAMPLES) * 6
        for _ in range(n_docs):
            doc_id = new_id("doc")
            s.db.execute("INSERT INTO documents (id, filename, sha256, size_bytes, status, created_at, updated_at)"
                         " VALUES (?,?,?,?,?,?,?)", (doc_id, "x.pdf", doc_id, 1, "review", now(), now()))
            s.db.execute("INSERT INTO sections (id, document_id, idx, title, text) VALUES (?,?,?,?,?)",
                         (new_id("sec"), doc_id, 0, "Bab", text))
            s.queue.enqueue("tts_generate", doc_id, {"engine": "espeak-ng"})
        t0 = time.perf_counter()
        procs = [subprocess.Popen([sys.executable, "-m", "app.worker"], cwd=ROOT, env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for _ in range(n_workers)]
        try:
            while time.perf_counter() - t0 < 600:
                left = s.db.one("SELECT COUNT(*) n FROM jobs WHERE status IN ('queued','running')")["n"]
                if not left:
                    break
                time.sleep(0.2)
        finally:
            for p in procs:
                p.terminate()
                p.wait(timeout=10)
        secs = time.perf_counter() - t0
        jobs = s.db.all("SELECT status, attempts, worker_id FROM jobs")
    return {"status": "MEASURED", "workers": n_workers, "jobs": len(jobs),
            "succeeded": sum(j["status"] == "succeeded" for j in jobs),
            "max_attempts_used": max(j["attempts"] for j in jobs),
            "distinct_workers_used": len({j["worker_id"] for j in jobs}), "seconds": round(secs, 2)}


BENCHES = {"pdf_reference": bench_pdf_reference, "ocr": bench_ocr, "pdf_large": bench_pdf_large,
           "tts": bench_tts, "asr": bench_asr, "concurrency": bench_concurrency}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench")
    ap.add_argument("--out", default=str(ROOT.parent / "eval-output"))
    ap.add_argument("args", nargs="*")
    a = ap.parse_args()
    if a.bench:
        out = BENCHES[a.bench](*a.args)
        # Peak RSS of this benchmark process itself (Linux reports KiB).
        out["peak_rss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
        # Largest external helper (ffmpeg / espeak-ng / tesseract / worker) it spawned.
        out["peak_rss_mb_largest_subprocess"] = round(
            resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024, 1)
        print(json.dumps(out, ensure_ascii=False))
        return

    results = {
        "environment": {"python": platform.python_version(), "machine": platform.machine(),
                        "cpus": os.cpu_count(), "system": platform.platform()},
        "pdf_reference": _measure("pdf_reference"),
        "ocr": _measure("ocr"),
        "pdf_large_300_pages": _measure("pdf_large", "300"),
        "tts": _measure("tts"),
        "asr": _measure("asr"),
        "diarization": {"status": "SKIPPED", "reason": "no diarization engine available"},
        "concurrency_1_worker": _measure("concurrency", "1"),
        "concurrency_2_workers": _measure("concurrency", "2"),
    }
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
