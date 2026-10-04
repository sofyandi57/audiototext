from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ..jobs import JobError
from .deps import get_services, not_found, require_auth

router = APIRouter(prefix="/api/jobs", dependencies=[Depends(require_auth)])


def _with_target(s, job: dict) -> dict:
    out = dict(job)
    table = "documents" if job["kind"] in ("pdf_extract", "tts_generate") else "meetings"
    row = s.db.one(f"SELECT filename FROM {table} WHERE id=?", (job["target_id"],))
    out["target_name"] = row["filename"] if row else None
    out["target_type"] = "document" if table == "documents" else "meeting"
    return out


@router.get("")
def list_jobs(request: Request, target_id: str | None = None, limit: int = 100):
    s = get_services(request)
    return [_with_target(s, j) for j in s.queue.list(target_id, min(max(limit, 1), 500))]


@router.get("/{job_id}")
def get_job(job_id: str, request: Request):
    s = get_services(request)
    job = s.queue.get(job_id)
    if not job:
        raise not_found("Pekerjaan")
    return _with_target(s, job)


@router.post("/{job_id}/retry", status_code=202)
def retry_job(job_id: str, request: Request):
    s = get_services(request)
    try:
        return s.queue.retry(job_id)
    except KeyError:
        raise not_found("Pekerjaan")
    except JobError as exc:
        raise HTTPException(409, exc.message)


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str, request: Request):
    s = get_services(request)
    job = s.queue.cancel(job_id)
    if not job:
        raise not_found("Pekerjaan")
    return job
