"""Job handlers for meeting transcription and analysis."""

from __future__ import annotations

import json
import logging

from ..asr import AsrUnavailable
from ..audio import ffmpeg
from ..db import new_id, now
from ..intelligence import run_analysis
from ..jobs import Handler, JobContext, JobError

log = logging.getLogger(__name__)


def _set_meeting(ctx: JobContext, meeting_id: str, **fields) -> None:
    fields["updated_at"] = now()
    cols = ", ".join(f"{k}=?" for k in fields)
    ctx.services.db.execute(f"UPDATE meetings SET {cols} WHERE id=?", (*fields.values(), meeting_id))


def prepare_audio(ctx: JobContext, meeting_id: str) -> tuple:
    """Convert to the internal 16 kHz mono WAV and a playback MP3 (idempotent)."""
    s = ctx.services
    src = s.storage.find_upload(meeting_id)
    if not src:
        raise JobError("File sumber tidak ditemukan; unggah ulang rekaman.")
    wav = s.storage.derived(meeting_id, "audio.wav")
    playback = s.storage.derived(meeting_id, "playback.mp3")
    try:
        if not wav.exists():
            ctx.report("mengonversi audio", 0.02)
            ffmpeg.to_wav16k(src, wav)
        if not playback.exists():
            ctx.report("menyiapkan pemutar audio", 0.05)
            ffmpeg.to_playback_mp3(wav, playback)
        info = ffmpeg.probe(wav)
    except ffmpeg.MediaError as exc:
        raise JobError(str(exc)) from exc
    _set_meeting(ctx, meeting_id, duration=info.duration)
    return wav, info.duration


def run_transcribe(ctx: JobContext) -> None:
    s = ctx.services
    meeting_id = ctx.job["target_id"]
    meeting = s.db.one("SELECT * FROM meetings WHERE id=?", (meeting_id,))
    if not meeting:
        raise JobError("Rapat sudah dihapus.")
    _set_meeting(ctx, meeting_id, status="converting", error=None)
    wav, duration = prepare_audio(ctx, meeting_id)

    asr_info = s.asr.info()
    if not asr_info.available:
        raise JobError(f"Transkripsi belum bisa dijalankan: {asr_info.reason}")
    _set_meeting(ctx, meeting_id, status="transcribing", asr_engine=asr_info.name,
                 asr_model=asr_info.model, language=ctx.params.get("language") or s.settings.asr_language)

    chunks = s.db.all("SELECT * FROM meeting_chunks WHERE meeting_id=? ORDER BY idx", (meeting_id,))
    if not chunks:
        plan = ffmpeg.plan_chunks(duration, s.settings.asr_chunk_seconds)
        if len(plan) > 1:
            ctx.report("mencari jeda untuk memotong audio", 0.07)
            plan = ffmpeg.snap_chunks(plan, ffmpeg.detect_silences(wav))
        with s.db.tx() as conn:
            for i, (a, b) in enumerate(plan):
                conn.execute("INSERT INTO meeting_chunks (meeting_id, idx, start, end) VALUES (?,?,?,?)",
                             (meeting_id, i, a, b))
        chunks = s.db.all("SELECT * FROM meeting_chunks WHERE meeting_id=? ORDER BY idx", (meeting_id,))

    language = ctx.params.get("language") or s.settings.asr_language
    prompt = ctx.params.get("glossary") or s.settings.asr_initial_prompt or None
    total = len(chunks)
    for ch in chunks:
        if ch["status"] == "done":
            continue  # resume: chunk already persisted
        ctx.report(f"mentranskripsi potongan {ch['idx'] + 1}/{total}", 0.1 + 0.85 * ch["idx"] / total)
        piece = s.storage.derived(meeting_id, f"chunk{ch['idx']:04d}.wav")
        try:
            ffmpeg.cut(wav, piece, ch["start"], ch["end"])
            segs = s.asr.transcribe(piece, language=language, initial_prompt=prompt)
        except AsrUnavailable as exc:
            raise JobError(str(exc)) from exc
        except ffmpeg.MediaError as exc:
            raise JobError(str(exc), retryable=True) from exc
        finally:
            piece.unlink(missing_ok=True)
        with s.db.tx() as conn:
            conn.execute("DELETE FROM segments WHERE meeting_id=? AND chunk_idx=?", (meeting_id, ch["idx"]))
            for j, seg in enumerate(segs):
                start = round(ch["start"] + seg.start, 3)
                end = round(min(ch["end"], ch["start"] + seg.end), 3)
                conn.execute(
                    "INSERT INTO segments (id, meeting_id, chunk_idx, idx, start, end, text, original_text,"
                    " confidence) VALUES (?,?,?,?,?,?,?,?,?)",
                    (new_id("seg"), meeting_id, ch["idx"], ch["idx"] * 100000 + j, start,
                     max(end, start), seg.text, seg.text, seg.confidence),
                )
            conn.execute("UPDATE meeting_chunks SET status='done', error=NULL WHERE meeting_id=? AND idx=?",
                         (meeting_id, ch["idx"]))

    # Normalise global order by time.
    rows = s.db.all("SELECT id FROM segments WHERE meeting_id=? ORDER BY start, idx", (meeting_id,))
    with s.db.tx() as conn:
        for i, r in enumerate(rows):
            conn.execute("UPDATE segments SET idx=? WHERE id=?", (i, r["id"]))

    d_info = s.diarization.info()
    if d_info.available:
        ctx.report("mengenali pembicara", 0.96)
        segs = s.db.all("SELECT id, start, end FROM segments WHERE meeting_id=? ORDER BY idx", (meeting_id,))
        labels = s.diarization.assign(wav, [(x["start"], x["end"]) for x in segs])
        with s.db.tx() as conn:
            for seg, label in zip(segs, labels):
                if label:
                    conn.execute("UPDATE segments SET speaker=? WHERE id=? AND edited=0", (label, seg["id"]))
    _set_meeting(ctx, meeting_id, status="ready", error=None,
                 diarization=d_info.name if d_info.available else "manual")
    s.queue.enqueue("meeting_analyze", meeting_id, {})


def transcribe_failed(ctx: JobContext, message: str) -> None:
    _set_meeting(ctx, ctx.job["target_id"], status="failed", error=message)


def run_analyze(ctx: JobContext) -> None:
    s = ctx.services
    meeting_id = ctx.job["target_id"]
    segments = s.db.all(
        "SELECT id, start, end, text, speaker FROM segments WHERE meeting_id=? ORDER BY idx", (meeting_id,))
    if not segments:
        raise JobError("Transkrip kosong; tidak ada yang bisa dianalisis.")
    engine = s.intelligence
    info = engine.info()
    if not info.get("available"):
        raise JobError(f"Analisis rapat tidak tersedia: {info.get('reason')}")
    ctx.report("menganalisis transkrip", 0.3)
    result = run_analysis(engine, segments)
    with s.db.tx() as conn:
        conn.execute("DELETE FROM insights WHERE meeting_id=?", (meeting_id,))
        for i, it in enumerate(result.items):
            conn.execute(
                "INSERT INTO insights (id, meeting_id, kind, text, owner, owner_confirmed, deadline,"
                " deadline_confirmed, segment_ids, start, end, engine, idx) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (new_id("ins"), meeting_id, it.kind, it.text, it.owner, int(it.owner_confirmed),
                 it.deadline, int(it.deadline_confirmed), json.dumps(it.segment_ids), it.start, it.end,
                 engine.name, i),
            )
    if result.rejected:
        log.info("analysis rejected %d unsupported items for %s", len(result.rejected), meeting_id)


HANDLERS = {
    "meeting_transcribe": Handler(run_transcribe, transcribe_failed),
    "meeting_analyze": Handler(run_analyze, None),
}
