from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from ..audio import ffmpeg
from ..db import new_id, now
from ..services import delete_meeting
from ..storage import UploadTooLarge
from .deps import get_services, not_found, require_auth

router = APIRouter(prefix="/api/meetings", dependencies=[Depends(require_auth)])

AUDIO_EXT = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".flac", ".wma", ".amr", ".3gp"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
ALLOWED = AUDIO_EXT | VIDEO_EXT


def fmt_ts(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _get(s, meeting_id: str) -> dict:
    m = s.db.one("SELECT * FROM meetings WHERE id=?", (meeting_id,))
    if not m:
        raise not_found("Rapat")
    return m


def _jobs(s, meeting_id: str) -> dict:
    out = {}
    for kind in ("meeting_transcribe", "meeting_analyze"):
        out[kind] = s.db.one(
            "SELECT * FROM jobs WHERE target_id=? AND kind=? ORDER BY created_at DESC LIMIT 1",
            (meeting_id, kind))
    return out


def _summary(s, m: dict) -> dict:
    out = dict(m)
    out["segment_count"] = s.db.one("SELECT COUNT(*) AS n FROM segments WHERE meeting_id=?", (m["id"],))["n"]
    out["job"] = s.queue.latest_for(m["id"])
    return out


@router.post("", status_code=201)
def upload_media(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form("", max_length=200),
    language: str = Form("id", max_length=8),
    glossary: str = Form("", max_length=1000),
):
    s = get_services(request)
    name = Path(file.filename or "rekaman").name[:200]
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED:
        raise HTTPException(415, "Format tidak didukung. Gunakan: " + ", ".join(sorted(ALLOWED)))
    if not re.fullmatch(r"[a-z]{2,3}|auto", language):
        raise HTTPException(422, "Kode bahasa tidak valid.")
    meeting_id = new_id("mtg")
    dest = s.storage.upload_path(meeting_id, ext)
    try:
        size, sha = s.storage.save_stream(file.file, dest, s.settings.max_media_mb * 1024 * 1024)
    except UploadTooLarge:
        raise HTTPException(413, f"File melebihi batas {s.settings.max_media_mb} MB.")
    try:
        info = ffmpeg.probe(dest)
    except ffmpeg.MediaError as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(415, str(exc))
    if not info.has_audio:
        dest.unlink(missing_ok=True)
        raise HTTPException(415, "File tidak memiliki trek audio.")
    if info.duration > s.settings.max_media_minutes * 60:
        dest.unlink(missing_ok=True)
        raise HTTPException(413, f"Durasi melebihi batas {s.settings.max_media_minutes} menit.")
    dup = s.db.one("SELECT * FROM meetings WHERE sha256=? ORDER BY created_at LIMIT 1", (sha,))
    if dup:
        dest.unlink(missing_ok=True)
        return {**_summary(s, dup), "duplicate": True}
    t = now()
    s.db.execute(
        "INSERT INTO meetings (id, filename, sha256, size_bytes, title, duration, status, language,"
        " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (meeting_id, name, sha, size, title.strip() or Path(name).stem, info.duration, "uploaded",
         None if language == "auto" else language, t, t))
    params = {"language": None if language == "auto" else language}
    if glossary.strip():
        params["glossary"] = glossary.strip()
    s.queue.enqueue("meeting_transcribe", meeting_id, params)
    return {**_summary(s, _get(s, meeting_id)), "duplicate": False}


@router.get("")
def list_meetings(request: Request):
    s = get_services(request)
    return [_summary(s, m) for m in s.db.all("SELECT * FROM meetings ORDER BY created_at DESC")]


@router.get("/{meeting_id}")
def get_meeting(meeting_id: str, request: Request):
    s = get_services(request)
    m = _get(s, meeting_id)
    out = _summary(s, m)
    segs = s.db.all("SELECT * FROM segments WHERE meeting_id=? ORDER BY idx", (meeting_id,))
    out["segments"] = segs
    speakers: dict[str, dict] = {}
    for seg in segs:
        key = seg["speaker"] or ""
        sp = speakers.setdefault(key, {"label": seg["speaker"], "segments": 0, "seconds": 0.0})
        sp["segments"] += 1
        sp["seconds"] += seg["end"] - seg["start"]
    out["speakers"] = list(speakers.values())
    insights = s.db.all("SELECT * FROM insights WHERE meeting_id=? ORDER BY kind, idx", (meeting_id,))
    for ins in insights:
        ins["segment_ids"] = json.loads(ins["segment_ids"])
        ins["owner_confirmed"] = bool(ins["owner_confirmed"])
        ins["deadline_confirmed"] = bool(ins["deadline_confirmed"])
    out["insights"] = insights
    out["jobs"] = _jobs(s, meeting_id)
    out["has_audio"] = s.storage.derived(meeting_id, "playback.mp3").exists()
    return out


class MeetingPatch(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


@router.patch("/{meeting_id}")
def rename_meeting(meeting_id: str, body: MeetingPatch, request: Request):
    s = get_services(request)
    _get(s, meeting_id)
    s.db.execute("UPDATE meetings SET title=?, updated_at=? WHERE id=?", (body.title.strip(), now(), meeting_id))
    return _summary(s, _get(s, meeting_id))


class SegmentPatch(BaseModel):
    text: str | None = Field(None, max_length=5000)
    speaker: str | None = Field(None, max_length=60)


@router.patch("/{meeting_id}/segments/{segment_id}")
def edit_segment(meeting_id: str, segment_id: str, body: SegmentPatch, request: Request):
    s = get_services(request)
    seg = s.db.one("SELECT * FROM segments WHERE id=? AND meeting_id=?", (segment_id, meeting_id))
    if not seg:
        raise not_found("Segmen")
    fields: dict = {}
    if body.text is not None:
        if not body.text.strip():
            raise HTTPException(422, "Teks segmen tidak boleh kosong.")
        fields["text"] = body.text.strip()
    if body.speaker is not None:
        fields["speaker"] = body.speaker.strip() or None
    if fields:
        fields["edited"] = 1
        cols = ", ".join(f"{k}=?" for k in fields)
        s.db.execute(f"UPDATE segments SET {cols} WHERE id=?", (*fields.values(), segment_id))
    return s.db.one("SELECT * FROM segments WHERE id=?", (segment_id,))


class SpeakerRename(BaseModel):
    old: str | None = Field(None, max_length=60)  # None/"" = unlabeled segments
    new: str = Field(..., min_length=1, max_length=60)


@router.post("/{meeting_id}/speakers/rename")
def rename_speaker(meeting_id: str, body: SpeakerRename, request: Request):
    s = get_services(request)
    _get(s, meeting_id)
    new = body.new.strip()
    if body.old:
        n = s.db.execute("UPDATE segments SET speaker=? WHERE meeting_id=? AND speaker=?",
                         (new, meeting_id, body.old))
    else:
        n = s.db.execute("UPDATE segments SET speaker=? WHERE meeting_id=? AND speaker IS NULL",
                         (new, meeting_id))
    return {"updated": n}


@router.post("/{meeting_id}/transcribe", status_code=202)
def transcribe(meeting_id: str, request: Request):
    s = get_services(request)
    m = _get(s, meeting_id)
    last = s.db.one("SELECT params FROM jobs WHERE target_id=? AND kind='meeting_transcribe'"
                    " ORDER BY created_at DESC LIMIT 1", (meeting_id,))
    params = json.loads(last["params"]) if last else {"language": m["language"]}
    return s.queue.enqueue("meeting_transcribe", meeting_id, params)


@router.post("/{meeting_id}/analyze", status_code=202)
def analyze(meeting_id: str, request: Request):
    s = get_services(request)
    _get(s, meeting_id)
    if not s.db.one("SELECT 1 FROM segments WHERE meeting_id=? LIMIT 1", (meeting_id,)):
        raise HTTPException(409, "Belum ada transkrip untuk dianalisis.")
    return s.queue.enqueue("meeting_analyze", meeting_id, {})


@router.get("/{meeting_id}/audio")
def meeting_audio(meeting_id: str, request: Request):
    s = get_services(request)
    _get(s, meeting_id)
    path = s.storage.derived(meeting_id, "playback.mp3")
    if not path.exists():
        raise not_found("Audio")
    return FileResponse(path, media_type="audio/mpeg")


@router.get("/{meeting_id}/export.{fmt}", response_class=PlainTextResponse)
def export(meeting_id: str, fmt: str, request: Request):
    s = get_services(request)
    m = _get(s, meeting_id)
    if fmt not in ("txt", "md"):
        raise not_found("Format")
    segs = s.db.all("SELECT * FROM segments WHERE meeting_id=? ORDER BY idx", (meeting_id,))
    insights = s.db.all("SELECT * FROM insights WHERE meeting_id=? ORDER BY kind, idx", (meeting_id,))
    body = render_markdown(m, segs, insights) if fmt == "md" else render_text(m, segs)
    media = "text/markdown; charset=utf-8" if fmt == "md" else "text/plain; charset=utf-8"
    name = re.sub(r"[^\w-]+", "-", (m["title"] or "rapat")).strip("-")[:60] or "rapat"
    return PlainTextResponse(body, media_type=media,
                             headers={"Content-Disposition": f'attachment; filename="{name}.{fmt}"'})


def render_text(m: dict, segs: list[dict]) -> str:
    lines = [m["title"] or m["filename"], ""]
    for seg in segs:
        who = f"{seg['speaker']}: " if seg["speaker"] else ""
        lines.append(f"[{fmt_ts(seg['start'])} - {fmt_ts(seg['end'])}] {who}{seg['text']}")
    return "\n".join(lines) + "\n"


KIND_TITLES = [("summary", "Ringkasan (ekstraktif)"), ("decision", "Keputusan"),
               ("action", "Tindak lanjut"), ("risk", "Risiko"), ("question", "Pertanyaan terbuka")]


def render_markdown(m: dict, segs: list[dict], insights: list[dict]) -> str:
    out = [f"# {m['title'] or m['filename']}", ""]
    if m.get("duration"):
        out += [f"Durasi: {fmt_ts(m['duration'])}", ""]
    for kind, title in KIND_TITLES:
        rows = [i for i in insights if i["kind"] == kind]
        if not rows:
            continue
        out += [f"## {title}", ""]
        for i in rows:
            extra = ""
            if kind == "action":
                owner = i["owner"] if i["owner_confirmed"] else "belum dikonfirmasi"
                deadline = i["deadline"] if i["deadline_confirmed"] else "belum dikonfirmasi"
                extra = f" — PIC: {owner}; tenggat: {deadline}"
            out.append(f"- [{fmt_ts(i['start'])}] {i['text']}{extra}")
        out.append("")
    out += ["## Transkrip", ""]
    for seg in segs:
        who = f"**{seg['speaker']}:** " if seg["speaker"] else ""
        out.append(f"- `{fmt_ts(seg['start'])}` {who}{seg['text']}")
    return "\n".join(out) + "\n"


@router.delete("/{meeting_id}")
def remove_meeting(meeting_id: str, request: Request):
    s = get_services(request)
    _get(s, meeting_id)
    delete_meeting(s, meeting_id)
    return {"deleted": meeting_id}
