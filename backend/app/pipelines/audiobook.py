"""Job handlers for the PDF-to-audiobook module."""

from __future__ import annotations

import hashlib
import json
import logging

from ..db import new_id, now
from ..jobs import Handler, JobContext, JobError
from ..pdf import PdfError, process_pdf
from ..tts import TTSUnavailable
from ..tts.pipeline import synthesize_section

log = logging.getLogger(__name__)


def text_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:32]


def _set_doc(ctx: JobContext, doc_id: str, **fields) -> None:
    fields["updated_at"] = now()
    cols = ", ".join(f"{k}=?" for k in fields)
    ctx.services.db.execute(f"UPDATE documents SET {cols} WHERE id=?", (*fields.values(), doc_id))


# -- extraction ---------------------------------------------------------------

def run_extract(ctx: JobContext) -> None:
    s = ctx.services
    doc_id = ctx.job["target_id"]
    doc = s.db.one("SELECT * FROM documents WHERE id=?", (doc_id,))
    if not doc:
        raise JobError("Dokumen sudah dihapus.")
    path = s.storage.find_upload(doc_id)
    if not path:
        raise JobError("File sumber tidak ditemukan; unggah ulang PDF.")
    _set_doc(ctx, doc_id, status="extracting", error=None)
    ctx.report("membaca PDF", 0.02)

    def progress(done: int, total: int) -> None:
        ctx.report(f"mengekstrak halaman {done}/{total}", 0.05 + 0.85 * done / total)

    try:
        result = process_pdf(
            path, s.ocr, min_page_chars=s.settings.min_page_chars,
            section_max_chars=s.settings.section_max_chars,
            max_pages=s.settings.max_pdf_pages, progress=progress,
        )
    except PdfError as exc:
        raise JobError(str(exc)) from exc

    ctx.report("menyusun bab", 0.95)
    with s.db.tx() as conn:
        conn.execute("DELETE FROM doc_pages WHERE document_id=?", (doc_id,))
        conn.execute("DELETE FROM sections WHERE document_id=?", (doc_id,))
        for p in result.pages:
            conn.execute(
                "INSERT INTO doc_pages (document_id, page_no, char_count, text_source, needs_review,"
                " review_reason) VALUES (?,?,?,?,?,?)",
                (doc_id, p.page_no, p.char_count, p.text_source, int(p.needs_review), p.review_reason),
            )
        for i, sec in enumerate(result.sections):
            conn.execute(
                "INSERT INTO sections (id, document_id, idx, title, level, text, start_page, end_page,"
                " needs_review) VALUES (?,?,?,?,?,?,?,?,?)",
                (new_id("sec"), doc_id, i, sec.title, sec.level, sec.text, sec.start_page,
                 sec.end_page, int(sec.needs_review)),
            )
        conn.execute(
            "UPDATE documents SET status='review', page_count=?, cleaning_report=?, ocr_available=?,"
            " error=NULL, updated_at=? WHERE id=?",
            (len(result.pages), json.dumps(result.report, ensure_ascii=False),
             int(bool(s.ocr and s.ocr.available())), now(), doc_id),
        )


def extract_failed(ctx: JobContext, message: str) -> None:
    _set_doc(ctx, ctx.job["target_id"], status="failed", error=message)


# -- speech generation --------------------------------------------------------

def engine_signature(engine: str, voice: str | None, rate: int | None) -> str:
    return f"{engine}|{voice or ''}|{rate or ''}"


def run_tts(ctx: JobContext) -> None:
    s = ctx.services
    doc_id = ctx.job["target_id"]
    params = ctx.params
    try:
        engine = s.tts_engine(params.get("engine"))
    except KeyError:
        raise JobError("Mesin TTS tidak dikenal.")
    info = engine.info()
    if not info.available:
        raise JobError(f"Mesin TTS '{engine.name}' tidak tersedia: {info.reason}")
    voice, rate = params.get("voice"), params.get("rate")
    signature = engine_signature(engine.name, voice, rate)

    wanted = params.get("section_ids")
    sections = s.db.all("SELECT * FROM sections WHERE document_id=? ORDER BY idx", (doc_id,))
    if wanted:
        sections = [x for x in sections if x["id"] in set(wanted)]
    if not sections:
        raise JobError("Tidak ada bagian untuk dibuatkan audio.")
    _set_doc(ctx, doc_id, status="generating", error=None)

    failed = 0
    for n, sec in enumerate(sections):
        ctx.report(f"membuat audio bagian {n + 1}/{len(sections)}", n / len(sections))
        text = sec["text"].strip()
        if not text:
            s.db.execute("UPDATE sections SET audio_status='skipped', audio_error=? WHERE id=?",
                         ("Bagian kosong — isi teks terlebih dahulu.", sec["id"]))
            continue
        out = s.storage.derived(doc_id, f"{sec['id']}.mp3")
        h = text_hash(text)
        if (sec["audio_status"] == "done" and sec["audio_text_hash"] == h
                and sec["audio_engine"] == signature and out.exists()):
            continue  # resume: already generated from identical text and settings
        try:
            duration = synthesize_section(engine, text, out, voice=voice, rate_wpm=rate)
        except TTSUnavailable as exc:
            raise JobError(str(exc)) from exc
        except Exception as exc:
            log.exception("TTS failed for section %s", sec["id"])
            failed += 1
            s.db.execute("UPDATE sections SET audio_status='failed', audio_error=? WHERE id=?",
                         ("Gagal membuat audio untuk bagian ini.", sec["id"]))
            continue
        s.db.execute(
            "UPDATE sections SET audio_status='done', audio_file=?, audio_duration=?, audio_engine=?,"
            " audio_text_hash=?, audio_error=NULL WHERE id=?",
            (out.name, duration, signature, h, sec["id"]),
        )
    # whole-book export is invalidated by any regeneration
    s.storage.derived(doc_id, "book.mp3").unlink(missing_ok=True)
    if failed:
        raise JobError(f"{failed} bagian gagal dibuatkan audio. Coba ulangi; bagian yang sudah"
                       " selesai tidak akan diproses ulang.", retryable=True)
    _refresh_doc_status(ctx, doc_id)


def _refresh_doc_status(ctx: JobContext, doc_id: str) -> None:
    rows = ctx.services.db.all(
        "SELECT audio_status, text FROM sections WHERE document_id=?", (doc_id,))
    pending = [r for r in rows if r["text"].strip() and r["audio_status"] != "done"]
    _set_doc(ctx, doc_id, status="review" if pending else "ready", error=None)


def tts_failed(ctx: JobContext, message: str) -> None:
    _set_doc(ctx, ctx.job["target_id"], status="review", error=message)


HANDLERS = {
    "pdf_extract": Handler(run_extract, extract_failed),
    "tts_generate": Handler(run_tts, tts_failed),
}
