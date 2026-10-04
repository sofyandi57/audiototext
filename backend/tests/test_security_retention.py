from __future__ import annotations

import pytest

from app.audio.ffmpeg import plan_chunks, snap_chunks
from app.db import now
from app.main import create_app
from app.services import apply_retention, build_services
from app.storage import Storage, StorageError

from . import corpus
from .conftest import FakeASR, drain


def test_storage_rejects_traversal(tmp_path):
    st = Storage(tmp_path / "u", tmp_path / "d")
    for bad in ["../etc", "doc_../../x", "doc_" + "g" * 20, ""]:
        with pytest.raises(StorageError):
            st.upload_path(bad, ".pdf")
    with pytest.raises(StorageError):
        st.derived("doc_" + "a" * 20, "..")
    with pytest.raises(StorageError):
        st.derived("doc_" + "a" * 20, "x/../../y")
    with pytest.raises(StorageError):
        st.upload_path("doc_" + "a" * 20, ".pdf/../x")


def test_unknown_or_malformed_ids_are_404(client):
    for url in ["/api/documents/doc_00000000000000000000", "/api/documents/..%2F..%2Fetc%2Fpasswd",
                "/api/meetings/mtg_00000000000000000000/audio", "/api/jobs/job_nope"]:
        assert client.get(url).status_code == 404


def test_uploads_are_not_served_statically(client, services, tmp_path):
    with open(corpus.make_book_pdf(tmp_path / "b.pdf"), "rb") as f:
        doc = client.post("/api/documents", files={"file": ("b.pdf", f)}).json()
    path = services.storage.find_upload(doc["id"])
    for url in [f"/uploads/{path.name}", f"/data/uploads/{path.name}", f"/{path.name}"]:
        r = client.get(url)
        assert r.status_code == 404 and not r.content.startswith(b"%PDF")


def test_access_token(tmp_path):
    from fastapi.testclient import TestClient

    from app.config import Settings

    settings = Settings(data_dir=tmp_path / "d", frontend_dir=tmp_path / "nf", access_token="s3cret",
                        run_worker_in_process=False, _env_file=None)
    app = create_app(services=build_services(settings, asr=FakeASR()), start_worker=False)
    with TestClient(app) as c:
        assert c.get("/api/health").status_code == 200  # health stays public
        assert c.get("/api/health").json()["auth_required"] is True
        assert c.get("/api/documents").status_code == 401
        assert c.get("/api/capabilities").status_code == 401
        assert c.get("/api/documents", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert c.get("/api/documents", headers={"Authorization": "Bearer s3cret"}).status_code == 200
        assert c.post("/api/auth", json={"token": "nope"}).status_code == 401
        r = c.post("/api/auth", json={"token": "s3cret"})
        assert r.status_code == 200 and "httponly" in r.headers["set-cookie"].lower()
        assert c.get("/api/documents").status_code == 200  # cookie (needed for <audio src>)
        c.delete("/api/auth")
        c.cookies.clear()
        assert c.get("/api/documents").status_code == 401


def test_retention_deletes_old_items_and_files(client, services, tmp_path):
    with open(corpus.make_book_pdf(tmp_path / "b.pdf"), "rb") as f:
        old = client.post("/api/documents", files={"file": ("b.pdf", f)}).json()
    with open(corpus.make_wrapped_pdf(tmp_path / "w.pdf"), "rb") as f:
        fresh = client.post("/api/documents", files={"file": ("w.pdf", f)}).json()
    drain(services)
    services.storage.derived(old["id"], "page00001.png").write_bytes(b"x")
    services.db.execute("UPDATE documents SET created_at=? WHERE id=?", (now() - 40 * 86400, old["id"]))
    assert apply_retention(services) == {"documents": 1, "meetings": 0}
    assert services.storage.find_upload(old["id"]) is None
    assert not services.storage.derived_root(old["id"]).exists()
    assert client.get(f"/api/documents/{old['id']}").status_code == 404
    assert client.get(f"/api/documents/{fresh['id']}").status_code == 200


def test_retention_disabled(services):
    services.settings.retention_days = 0
    assert apply_retention(services) == {"documents": 0, "meetings": 0}


def test_delete_document_cancels_jobs(client, services, tmp_path):
    with open(corpus.make_book_pdf(tmp_path / "b.pdf"), "rb") as f:
        doc = client.post("/api/documents", files={"file": ("b.pdf", f)}).json()
    client.delete(f"/api/documents/{doc['id']}")
    assert services.queue.get(doc["job"]["id"])["status"] == "cancelled"
    assert drain(services) == 0


def test_errors_do_not_leak_internals(services, monkeypatch):
    from fastapi.testclient import TestClient

    def boom(*a, **k):
        raise RuntimeError("/srv/secret/path sqlite internals")

    monkeypatch.setattr(services.queue, "list", boom)
    with TestClient(create_app(services=services, start_worker=False), raise_server_exceptions=False) as c:
        r = c.get("/api/jobs")
    assert r.status_code == 500 and "secret" not in r.text


def test_chunk_planning_and_silence_snapping():
    assert plan_chunks(0, 300) == []
    assert plan_chunks(302, 300) == [(0, 302)]  # no tiny trailing chunk
    assert plan_chunks(650, 300) == [(0, 300), (300, 600), (600, 650)]
    snapped = snap_chunks([(0, 300), (300, 600), (600, 650)], [(288.0, 289.0), (610.0, 611.0)])
    assert snapped == [(0, 288.5), (288.5, 610.5), (610.5, 650)]
