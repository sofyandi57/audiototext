from __future__ import annotations

import hmac
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from .. import __version__
from ..audio import ffmpeg
from .deps import COOKIE, get_services, is_authenticated, require_auth

router = APIRouter(prefix="/api")


@router.get("/health")
def health(request: Request):
    s = get_services(request)
    try:
        s.db.one("SELECT 1 AS ok")
        db_ok = True
    except Exception:
        db_ok = False
    worker = getattr(request.app.state, "worker_thread", None)
    counts = {r["status"]: r["n"] for r in s.db.all(
        "SELECT status, COUNT(*) AS n FROM jobs WHERE status IN ('queued','running') GROUP BY status")}
    return {
        "status": "ok" if db_ok else "degraded",
        "version": __version__,
        "database": db_ok,
        "ffmpeg": ffmpeg.available(),
        "worker": {
            "in_process": s.settings.run_worker_in_process,
            "alive": bool(worker and worker.is_alive()) if s.settings.run_worker_in_process else None,
        },
        "queue": {"queued": counts.get("queued", 0), "running": counts.get("running", 0)},
        "auth_required": bool(s.settings.access_token),
    }


@router.get("/capabilities", dependencies=[Depends(require_auth)])
def capabilities(request: Request):
    s = get_services(request)
    tts = [asdict(e.info()) for e in s.tts.values()]
    asr = asdict(s.asr.info())
    return {
        "ffmpeg": ffmpeg.available(),
        "ocr": s.ocr.describe() if s.ocr else {"available": False, "reason": "OCR dinonaktifkan."},
        "tts": tts,
        "tts_default": s.settings.tts_engine,
        "browser_tts_preview": True,
        "asr": asr,
        "diarization": asdict(s.diarization.info()),
        "intelligence": s.intelligence.info(),
        "limits": {
            "max_pdf_mb": s.settings.max_pdf_mb,
            "max_media_mb": s.settings.max_media_mb,
            "max_pdf_pages": s.settings.max_pdf_pages,
            "max_media_minutes": s.settings.max_media_minutes,
        },
        "retention_days": s.settings.retention_days,
    }


class TokenIn(BaseModel):
    token: str


@router.get("/auth")
def auth_status(request: Request):
    s = get_services(request)
    return {"required": bool(s.settings.access_token), "authenticated": is_authenticated(request)}


@router.post("/auth")
def login(body: TokenIn, request: Request, response: Response):
    s = get_services(request)
    if not s.settings.access_token:
        return {"required": False, "authenticated": True}
    if not hmac.compare_digest(body.token.encode(), s.settings.access_token.encode()):
        raise HTTPException(status_code=401, detail="Token salah.")
    response.set_cookie(COOKIE, body.token, httponly=True, samesite="lax",
                        secure=request.url.scheme == "https", max_age=60 * 60 * 24 * 30)
    return {"required": True, "authenticated": True}


@router.delete("/auth")
def logout(response: Response):
    response.delete_cookie(COOKIE)
    return {"ok": True}
