from __future__ import annotations

import json
import re
from pathlib import Path

import pymupdf
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from ..audio import ffmpeg
from ..db import new_id, now
from ..pipelines.audiobook import text_hash
from ..services import delete_document
from ..storage import UploadTooLarge
from .deps import get_services, not_found, require_auth

router = APIRouter(prefix="/api/documents", dependencies=[Depends(require_auth)])


def _section_out(sec: dict) -> dict:
    out = dict(sec)
    out["audio_stale"] = bool(sec["audio_status"] == "done" and sec["audio_text_hash"] != text_hash(sec["text"]))
    out["char_count"] = len(sec["text"])
    out.pop("audio_file", None)
    return out


def _doc_summary(s, doc: dict) -> dict:
    out = dict(doc)
    out.pop("cleaning_report", None)
    out["job"] = s.queue.latest_for(doc["id"])
    stats = s.db.one(
        "SELECT COUNT(*) AS sections, SUM(audio_status='done') AS with_audio, SUM(needs_review) AS needs_review"
        " FROM sections WHERE document_id=?", (doc["id"],))
    out.update({k: v or 0 for k, v in stats.items()})
    return out


def _get_doc(s, doc_id: str) -> dict:
    doc = s.db.one("SELECT * FROM documents WHERE id=?", (doc_id,))
    if not doc:
        raise not_found("Dokumen")
    return doc


@router.post("", status_code=201)
def upload_pdf(request: Request, file: UploadFile = File(...)):
    s = get_services(request)
    name = Path(file.filename or "dokumen.pdf").name[:200]
    if not name.lower().endswith(".pdf"):
        raise HTTPException(415, "Hanya file PDF (.pdf) yang didukung.")
    head = file.file.read(1024)
    file.file.seek(0)
    if b"%PDF-" not in head:
        raise HTTPException(415, "File ini bukan PDF yang valid.")
    doc_id = new_id("doc")
    dest = s.storage.upload_path(doc_id, ".pdf")
    try:
        size, sha = s.storage.save_stream(file.file, dest, s.settings.max_pdf_mb * 1024 * 1024)
    except UploadTooLarge:
        raise HTTPException(413, f"PDF melebihi batas {s.settings.max_pdf_mb} MB.")
    dup = s.db.one("SELECT * FROM documents WHERE sha256=? ORDER BY created_at LIMIT 1", (sha,))
    if dup:
        dest.unlink(missing_ok=True)
        return {**_doc_summary(s, dup), "duplicate": True}
    t = now()
    s.db.execute(
        "INSERT INTO documents (id, filename, sha256, size_bytes, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?)", (doc_id, name, sha, size, "uploaded", t, t))
    s.queue.enqueue("pdf_extract", doc_id)
    return {**_doc_summary(s, _get_doc(s, doc_id)), "duplicate": False}


@router.get("")
def list_documents(request: Request):
    s = get_services(request)
    docs = s.db.all("SELECT * FROM documents ORDER BY created_at DESC")
    return [_doc_summary(s, d) for d in docs]


@router.get("/{doc_id}")
def get_document(doc_id: str, request: Request):
    s = get_services(request)
    doc = _get_doc(s, doc_id)
    out = _doc_summary(s, doc)
    out["cleaning_report"] = json.loads(doc["cleaning_report"]) if doc["cleaning_report"] else None
    out["pages"] = s.db.all("SELECT * FROM doc_pages WHERE document_id=? ORDER BY page_no", (doc_id,))
    out["sections"] = [_section_out(x) for x in s.db.all(
        "SELECT * FROM sections WHERE document_id=? ORDER BY idx", (doc_id,))]
    out["jobs"] = s.queue.list(doc_id, limit=10)
    return out


class SectionPatch(BaseModel):
    title: str | None = Field(None, max_length=300)
    text: str | None = Field(None, max_length=200_000)
    needs_review: bool | None = None


@router.patch("/{doc_id}/sections/{section_id}")
def edit_section(doc_id: str, section_id: str, body: SectionPatch, request: Request):
    s = get_services(request)
    sec = s.db.one("SELECT * FROM sections WHERE id=? AND document_id=?", (section_id, doc_id))
    if not sec:
        raise not_found("Bagian")
    fields: dict = {}
    if body.title is not None:
        fields["title"] = body.title.strip() or sec["title"]
    if body.text is not None:
        fields["text"] = body.text.replace("\r\n", "\n")
        fields["edited"] = 1
    if body.needs_review is not None:
        fields["needs_review"] = int(body.needs_review)
    if fields:
        cols = ", ".join(f"{k}=?" for k in fields)
        s.db.execute(f"UPDATE sections SET {cols} WHERE id=?", (*fields.values(), section_id))
        s.db.execute("UPDATE documents SET updated_at=? WHERE id=?", (now(), doc_id))
    return _section_out(s.db.one("SELECT * FROM sections WHERE id=?", (section_id,)))


class ExtractIn(BaseModel):
    discard_edits: bool = False


@router.post("/{doc_id}/extract", status_code=202)
def re_extract(doc_id: str, body: ExtractIn, request: Request):
    s = get_services(request)
    _get_doc(s, doc_id)
    edited = s.db.one("SELECT COUNT(*) AS n FROM sections WHERE document_id=? AND edited=1", (doc_id,))["n"]
    if edited and not body.discard_edits:
        raise HTTPException(409, f"{edited} bagian sudah diedit dan akan hilang. Konfirmasi untuk melanjutkan.")
    return s.queue.enqueue("pdf_extract", doc_id)


class TtsIn(BaseModel):
    engine: str | None = None
    voice: str | None = Field(None, max_length=50)
    rate: int | None = Field(None, ge=80, le=400)
    section_ids: list[str] | None = None


@router.post("/{doc_id}/tts", status_code=202)
def generate_audio(doc_id: str, body: TtsIn, request: Request):
    s = get_services(request)
    doc = _get_doc(s, doc_id)
    if doc["status"] in ("uploaded", "extracting", "failed"):
        raise HTTPException(409, "Teks belum siap. Tunggu ekstraksi selesai atau perbaiki kesalahan.")
    try:
        engine = s.tts_engine(body.engine)
    except KeyError:
        raise HTTPException(400, "Mesin TTS tidak dikenal.")
    info = engine.info()
    if not info.available:
        raise HTTPException(409, f"Mesin TTS '{engine.name}' tidak tersedia: {info.reason}")
    params = {"engine": engine.name, "voice": body.voice or s.settings.tts_voice,
              "rate": body.rate or s.settings.tts_rate_wpm}
    if body.section_ids:
        params["section_ids"] = sorted(body.section_ids)
    return s.queue.enqueue("tts_generate", doc_id, params)


@router.get("/{doc_id}/file")
def download_pdf(doc_id: str, request: Request):
    s = get_services(request)
    doc = _get_doc(s, doc_id)
    path = s.storage.find_upload(doc_id)
    if not path:
        raise not_found("File")
    return FileResponse(path, media_type="application/pdf", filename=doc["filename"],
                        content_disposition_type="inline")


@router.get("/{doc_id}/pages/{page_no}/preview")
def page_preview(doc_id: str, page_no: int, request: Request):
    """Server-rendered page image: works on every mobile browser (no PDF viewer needed)."""
    s = get_services(request)
    doc = _get_doc(s, doc_id)
    if not doc["page_count"] or not 1 <= page_no <= doc["page_count"]:
        raise not_found("Halaman")
    out = s.storage.derived(doc_id, f"page{page_no:05d}.png")
    if not out.exists():
        path = s.storage.find_upload(doc_id)
        if not path:
            raise not_found("File")
        with pymupdf.open(path) as pdf:
            page = pdf.load_page(page_no - 1)
            zoom = min(2.0, 900 / max(page.rect.width, 1))
            page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).save(out)
    return FileResponse(out, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/{doc_id}/sections/{section_id}/audio")
def section_audio(doc_id: str, section_id: str, request: Request, download: bool = False):
    s = get_services(request)
    sec = s.db.one("SELECT * FROM sections WHERE id=? AND document_id=?", (section_id, doc_id))
    if not sec or sec["audio_status"] != "done" or not sec["audio_file"]:
        raise not_found("Audio")
    path = s.storage.derived(doc_id, sec["audio_file"])
    if not path.exists():
        raise not_found("Audio")
    name = f"{sec['idx'] + 1:03d}-{_slug(sec['title'])}.mp3"
    return FileResponse(path, media_type="audio/mpeg", filename=name,
                        content_disposition_type="attachment" if download else "inline")


@router.get("/{doc_id}/audiobook.mp3")
def full_audiobook(doc_id: str, request: Request):
    s = get_services(request)
    doc = _get_doc(s, doc_id)
    sections = s.db.all("SELECT * FROM sections WHERE document_id=? ORDER BY idx", (doc_id,))
    with_text = [x for x in sections if x["text"].strip()]
    missing = [x for x in with_text if x["audio_status"] != "done"]
    if not with_text or missing:
        raise HTTPException(409, f"{len(missing)} bagian belum memiliki audio.")
    out = s.storage.derived(doc_id, "book.mp3")
    parts = [s.storage.derived(doc_id, x["audio_file"]) for x in with_text]
    if not out.exists() or any(p.stat().st_mtime > out.stat().st_mtime for p in parts):
        ffmpeg.concat_copy(parts, out)
    return FileResponse(out, media_type="audio/mpeg", filename=f"{_slug(Path(doc['filename']).stem)}.mp3")


@router.get("/{doc_id}/text.txt", response_class=PlainTextResponse)
def export_text(doc_id: str, request: Request):
    s = get_services(request)
    _get_doc(s, doc_id)
    sections = s.db.all("SELECT title, text FROM sections WHERE document_id=? ORDER BY idx", (doc_id,))
    return "\n\n".join(f"{x['title']}\n\n{x['text']}" for x in sections) + "\n"


@router.delete("/{doc_id}")
def remove_document(doc_id: str, request: Request):
    s = get_services(request)
    _get_doc(s, doc_id)
    delete_document(s, doc_id)
    return {"deleted": doc_id}


def _slug(text: str) -> str:
    t = re.sub(r"[^\w]+", "-", text.lower()).strip("-")
    return (t or "audio")[:60]

