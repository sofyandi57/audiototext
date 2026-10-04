"""End-to-end PDF -> review -> edit -> audio -> download, through the HTTP API."""

from __future__ import annotations

import io

from app.audio import ffmpeg

from . import corpus
from .conftest import drain, requires_espeak


def _upload(client, path, name="buku.pdf"):
    with open(path, "rb") as f:
        return client.post("/api/documents", files={"file": (name, f, "application/pdf")})


def test_upload_success_is_not_extraction_success(client, services, tmp_path):
    r = _upload(client, corpus.make_book_pdf(tmp_path / "b.pdf"))
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "uploaded" and body["job"]["status"] == "queued"
    assert client.get(f"/api/documents/{body['id']}").json()["sections"] == []


@requires_espeak
def test_full_audiobook_flow(client, services, tmp_path):
    doc_id = _upload(client, corpus.make_book_pdf(tmp_path / "b.pdf")).json()["id"]
    assert drain(services) == 1
    doc = client.get(f"/api/documents/{doc_id}").json()
    assert doc["status"] == "review" and doc["page_count"] == 3
    assert [s["title"] for s in doc["sections"]][0] == "BAB I PENDAHULUAN"
    assert doc["cleaning_report"]["summary"]["header"] == 3

    # user correction before audio generation
    sec = doc["sections"][0]
    new_text = sec["text"] + "\n\nKalimat tambahan dari pengguna."
    r = client.patch(f"/api/documents/{doc_id}/sections/{sec['id']}", json={"text": new_text})
    assert r.status_code == 200 and r.json()["edited"] == 1

    r = client.post(f"/api/documents/{doc_id}/tts", json={"engine": "espeak-ng", "rate": 180})
    assert r.status_code == 202
    job_id = r.json()["id"]
    # duplicate click returns the same job
    assert client.post(f"/api/documents/{doc_id}/tts", json={"engine": "espeak-ng", "rate": 180}).json()["id"] == job_id
    drain(services)
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "succeeded"
    doc = client.get(f"/api/documents/{doc_id}").json()
    assert doc["status"] == "ready" and doc["with_audio"] == 3
    assert all(s["audio_duration"] > 1 for s in doc["sections"])

    audio = client.get(f"/api/documents/{doc_id}/sections/{sec['id']}/audio")
    assert audio.status_code == 200 and audio.headers["content-type"] == "audio/mpeg"
    ranged = client.get(f"/api/documents/{doc_id}/sections/{sec['id']}/audio", headers={"Range": "bytes=0-99"})
    assert ranged.status_code == 206 and len(ranged.content) == 100
    dl = client.get(f"/api/documents/{doc_id}/sections/{sec['id']}/audio?download=1")
    assert "attachment" in dl.headers["content-disposition"]

    book = client.get(f"/api/documents/{doc_id}/audiobook.mp3")
    assert book.status_code == 200
    out = tmp_path / "book.mp3"
    out.write_bytes(book.content)
    total = sum(s["audio_duration"] for s in doc["sections"])
    assert abs(ffmpeg.probe(out).duration - total) < 1.0

    # editing after generation marks audio stale; regeneration only redoes that section
    client.patch(f"/api/documents/{doc_id}/sections/{sec['id']}", json={"text": "Teks baru singkat."})
    doc = client.get(f"/api/documents/{doc_id}").json()
    assert [s["audio_stale"] for s in doc["sections"]] == [True, False, False]

    txt = client.get(f"/api/documents/{doc_id}/text.txt")
    assert "Teks baru singkat." in txt.text


def test_tts_resume_only_regenerates_failed_sections(client, services, tmp_path):
    from .test_tts import ToneEngine

    class FlakyTone(ToneEngine):
        name = "espeak-ng"
        fail_next = True

        def synthesize(self, text, out_wav, voice=None, rate_wpm=None):
            if "METODOLOGI" in text or "sintetis" in text:
                if FlakyTone.fail_next:
                    FlakyTone.fail_next = False
                    raise RuntimeError("transient")
            super().synthesize(text, out_wav, voice, rate_wpm)

    eng = FlakyTone()
    services.tts["espeak-ng"] = eng
    doc_id = _upload(client, corpus.make_book_pdf(tmp_path / "b.pdf")).json()["id"]
    drain(services)
    job = client.post(f"/api/documents/{doc_id}/tts", json={"engine": "espeak-ng"}).json()
    drain(services)  # first attempt fails one section, auto-retry resumes
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "succeeded"
    texts = eng.inputs
    # chapter 1 and 3 synthesised once; chapter 2 only on the retry
    assert sum("Proyek Nusantara" in t for t in texts) == 1
    assert sum("Hasil awal" in t for t in texts) == 1
    assert client.get(f"/api/documents/{doc_id}").json()["status"] == "ready"


def test_review_pages_are_visible(client, services, tmp_path):
    services.ocr = None
    doc_id = _upload(client, corpus.make_scanned_pdf(tmp_path / "s.pdf")).json()["id"]
    drain(services)
    doc = client.get(f"/api/documents/{doc_id}").json()
    assert doc["pages"][0]["needs_review"] == 1
    assert doc["sections"][0]["needs_review"] == 1 and doc["needs_review"] == 1


def test_upload_validation(client, services, tmp_path):
    r = client.post("/api/documents", files={"file": ("a.txt", b"hello", "text/plain")})
    assert r.status_code == 415
    r = client.post("/api/documents", files={"file": ("a.pdf", b"not a pdf at all", "application/pdf")})
    assert r.status_code == 415
    services.settings.max_pdf_mb = 1
    big = b"%PDF-1.4\n" + b"0" * (1024 * 1024 + 10)
    r = client.post("/api/documents", files={"file": ("big.pdf", io.BytesIO(big), "application/pdf")})
    assert r.status_code == 413
    assert not list(services.storage.uploads_dir.iterdir())  # nothing left behind


def test_malformed_pdf_job_fails_with_actionable_message(client, services, tmp_path):
    doc = _upload(client, corpus.make_malformed_pdf(tmp_path / "m.pdf")).json()
    drain(services)
    d = client.get(f"/api/documents/{doc['id']}").json()
    assert d["status"] == "failed" and "rusak" in d["error"]
    assert d["job"]["status"] == "failed"


def test_duplicate_upload_returns_existing(client, services, tmp_path):
    path = corpus.make_book_pdf(tmp_path / "b.pdf")
    a = _upload(client, path).json()
    b = _upload(client, path).json()
    assert b["duplicate"] is True and a["id"] == b["id"]
    assert len(client.get("/api/documents").json()) == 1


def test_page_preview_and_pdf_download(client, services, tmp_path):
    doc_id = _upload(client, corpus.make_book_pdf(tmp_path / "b.pdf")).json()["id"]
    drain(services)
    img = client.get(f"/api/documents/{doc_id}/pages/1/preview")
    assert img.status_code == 200 and img.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert client.get(f"/api/documents/{doc_id}/pages/99/preview").status_code == 404
    pdf = client.get(f"/api/documents/{doc_id}/file")
    assert pdf.content.startswith(b"%PDF")


def test_reextract_requires_confirmation_when_edited(client, services, tmp_path):
    doc_id = _upload(client, corpus.make_book_pdf(tmp_path / "b.pdf")).json()["id"]
    drain(services)
    sec = client.get(f"/api/documents/{doc_id}").json()["sections"][0]
    client.patch(f"/api/documents/{doc_id}/sections/{sec['id']}", json={"text": "ubah"})
    assert client.post(f"/api/documents/{doc_id}/extract", json={}).status_code == 409
    assert client.post(f"/api/documents/{doc_id}/extract", json={"discard_edits": True}).status_code == 202


def test_tts_rejected_before_extraction(client, services, tmp_path):
    doc_id = _upload(client, corpus.make_book_pdf(tmp_path / "b.pdf")).json()["id"]
    assert client.post(f"/api/documents/{doc_id}/tts", json={}).status_code == 409
    drain(services)
    assert client.post(f"/api/documents/{doc_id}/tts", json={"engine": "nope"}).status_code == 400
    assert client.post(f"/api/documents/{doc_id}/tts", json={"engine": "piper"}).status_code == 409
