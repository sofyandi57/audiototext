"""Meeting upload -> conversion -> chunked ASR -> editing -> analysis -> export."""

from __future__ import annotations

import json

import pytest

from app.audio import ffmpeg
from app.db import new_id

from . import corpus
from .conftest import FakeASR, drain, requires_ffmpeg

pytestmark = requires_ffmpeg


def _upload(client, path, **form):
    with open(path, "rb") as f:
        return client.post("/api/meetings", files={"file": (path.name, f)}, data=form)


def test_rejects_unsupported_and_audioless_files(client, services, tmp_path):
    r = client.post("/api/meetings", files={"file": ("notes.txt", b"hi")})
    assert r.status_code == 415
    r = client.post("/api/meetings", files={"file": ("fake.mp3", b"this is text, not audio")})
    assert r.status_code == 415
    silent_video = tmp_path / "v.mp4"
    import subprocess
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=red:s=64x64:d=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(silent_video)], check=True)
    r = _upload(client, silent_video)
    assert r.status_code == 415 and "audio" in r.json()["detail"]
    assert not list(services.storage.uploads_dir.iterdir())


def test_duration_limit(client, services, tmp_path):
    services.settings.max_media_minutes = 0
    r = _upload(client, corpus.make_tone(tmp_path / "t.wav", 2))
    assert r.status_code == 413


def test_video_is_converted_and_timestamps_offset_per_chunk(client, services, fake_asr, tmp_path):
    video = corpus.make_tone(tmp_path / "rapat.mp4", seconds=25, video=True)
    m = _upload(client, video, title="Rapat Mingguan").json()
    assert m["status"] == "uploaded" and m["title"] == "Rapat Mingguan"
    drain(services)
    d = client.get(f"/api/meetings/{m['id']}").json()
    assert d["status"] == "ready", d["error"]
    assert d["duration"] == pytest.approx(25, abs=0.2)
    wav = services.storage.derived(m["id"], "audio.wav")
    info = ffmpeg.probe(wav)
    assert info.has_audio and not info.has_video
    chunks = services.db.all("SELECT * FROM meeting_chunks WHERE meeting_id=? ORDER BY idx", (m["id"],))
    bounds = [(c["start"], c["end"]) for c in chunks]
    assert bounds[:2] == [(0, 10), (10, 20)] and bounds[2][0] == 20
    assert bounds[2][1] == pytest.approx(25, abs=0.05)
    segs = d["segments"]
    assert [s["start"] for s in segs] == [0.5, 3.0, 10.5, 13.0, 20.5, 23.0]
    assert [s["end"] for s in segs] == [2.0, 4.5, 12.0, 14.5, 22.0, 24.5]
    assert [s["idx"] for s in segs] == list(range(6))
    assert d["has_audio"] and client.get(f"/api/meetings/{m['id']}/audio").status_code == 200
    # analysis job was chained automatically
    assert d["jobs"]["meeting_analyze"]["status"] == "succeeded"


def test_chunk_failure_resumes_without_redoing_finished_chunks(client, services, tmp_path):
    services.asr = asr = FakeASR(fail_on_call={2})
    m = _upload(client, corpus.make_tone(tmp_path / "a.wav", 25)).json()
    drain(services)
    d = client.get(f"/api/meetings/{m['id']}").json()
    assert d["status"] == "ready"
    # 3 chunks, one crash: 4 calls total, chunk 0 not re-transcribed
    assert asr.calls == 4
    assert len(d["segments"]) == 6
    job = d["jobs"]["meeting_transcribe"]
    assert job["status"] == "succeeded" and job["attempts"] == 2


def test_asr_unavailable_is_explicit_and_retryable(client, services, tmp_path):
    services.asr = FakeASR(available=False)
    m = _upload(client, corpus.make_tone(tmp_path / "a.wav", 3)).json()
    drain(services)
    d = client.get(f"/api/meetings/{m['id']}").json()
    assert d["status"] == "failed" and "Transkripsi belum bisa dijalankan" in d["error"]
    assert d["has_audio"]  # playback still works without ASR
    job = d["jobs"]["meeting_transcribe"]
    assert job["status"] == "failed" and job["attempts"] == 1
    services.asr = FakeASR()
    r = client.post(f"/api/jobs/{job['id']}/retry")
    assert r.status_code == 202 and r.json()["id"] == job["id"]
    drain(services)
    assert client.get(f"/api/meetings/{m['id']}").json()["status"] == "ready"


def _seed_meeting(services, texts: list[tuple[str | None, str]]) -> tuple[str, list[str]]:
    mid = new_id("mtg")
    services.db.execute(
        "INSERT INTO meetings (id, filename, sha256, size_bytes, title, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?)", (mid, "x.wav", "sha" + mid, 1, "Uji", "ready", 0, 0))
    ids = []
    for i, (spk, text) in enumerate(texts):
        sid = new_id("seg")
        ids.append(sid)
        services.db.execute(
            "INSERT INTO segments (id, meeting_id, chunk_idx, idx, start, end, text, original_text, speaker)"
            " VALUES (?,?,?,?,?,?,?,?,?)", (sid, mid, 0, i, i * 10.0, i * 10.0 + 8, text, text, spk))
    return mid, ids


def test_speaker_label_editing_and_rename(client, services):
    mid, ids = _seed_meeting(services, [(None, "Halo semua."), (None, "Baik, mulai."), ("SPEAKER_1", "Oke.")])
    r = client.patch(f"/api/meetings/{mid}/segments/{ids[0]}", json={"speaker": "Rina"})
    assert r.json()["speaker"] == "Rina" and r.json()["edited"] == 1
    assert client.post(f"/api/meetings/{mid}/speakers/rename", json={"old": None, "new": "Budi"}).json()["updated"] == 1
    assert client.post(f"/api/meetings/{mid}/speakers/rename", json={"old": "SPEAKER_1", "new": "Sari"}).json()["updated"] == 1
    d = client.get(f"/api/meetings/{mid}").json()
    assert [s["speaker"] for s in d["segments"]] == ["Rina", "Budi", "Sari"]
    assert {sp["label"] for sp in d["speakers"]} == {"Rina", "Budi", "Sari"}
    # text edit keeps the original ASR output and the timestamp
    client.patch(f"/api/meetings/{mid}/segments/{ids[1]}", json={"text": "Baik, kita mulai."})
    seg = client.get(f"/api/meetings/{mid}").json()["segments"][1]
    assert seg["text"] == "Baik, kita mulai." and seg["original_text"] == "Baik, mulai." and seg["start"] == 10.0
    assert client.patch(f"/api/meetings/{mid}/segments/{ids[1]}", json={"text": "  "}).status_code == 422


def test_exports_include_timestamps_and_speakers(client, services):
    mid, _ = _seed_meeting(services, [("Rina", "Kita sepakat memakai SQLite."),
                                      ("Budi", "Tolong Sari kirim laporan paling lambat Jumat.")])
    client.post(f"/api/meetings/{mid}/analyze")
    drain(services)
    txt = client.get(f"/api/meetings/{mid}/export.txt")
    assert "[00:00 - 00:08] Rina: Kita sepakat memakai SQLite." in txt.text
    assert "attachment" in txt.headers["content-disposition"]
    md = client.get(f"/api/meetings/{mid}/export.md").text
    assert "## Keputusan" in md and "- [00:00] Kita sepakat memakai SQLite." in md
    assert "PIC: Sari; tenggat: paling lambat Jumat" in md
    assert "`00:10` **Budi:**" in md


def test_action_items_have_provenance(client, services):
    mid, ids = _seed_meeting(services, [
        ("Rina", "Selamat pagi, kita mulai rapat evaluasi aplikasi transkripsi hari ini."),
        ("Budi", "Setelah diskusi panjang kita sepakat memakai FastAPI untuk backend."),
        ("Rina", "Tolong Budi siapkan dokumentasi API paling lambat hari Jumat."),
        ("Sari", "Dokumentasi deployment perlu diperbarui oleh tim."),
        (None, "Saya akan menguji model di CPU."),
    ])
    client.post(f"/api/meetings/{mid}/analyze")
    drain(services)
    d = client.get(f"/api/meetings/{mid}").json()
    by_id = {s["id"]: s for s in d["segments"]}
    assert d["insights"], "analysis produced nothing"
    for ins in d["insights"]:
        assert ins["segment_ids"] and all(i in by_id for i in ins["segment_ids"])
        cited = [by_id[i] for i in ins["segment_ids"]]
        assert ins["start"] == min(c["start"] for c in cited)
        assert ins["text"] in " ".join(c["text"] for c in cited)  # quoted, not invented
    actions = {a["text"]: a for a in d["insights"] if a["kind"] == "action"}
    a = actions["Tolong Budi siapkan dokumentasi API paling lambat hari Jumat."]
    assert a["owner"] == "Budi" and a["owner_confirmed"] and a["deadline_confirmed"]
    b = actions["Dokumentasi deployment perlu diperbarui oleh tim."]
    assert b["owner"] is None and not b["owner_confirmed"] and not b["deadline_confirmed"]
    c = actions["Saya akan menguji model di CPU."]
    assert c["owner"] is None and not c["owner_confirmed"]  # unknown speaker => unconfirmed
    decisions = [i["text"] for i in d["insights"] if i["kind"] == "decision"]
    assert decisions == ["Setelah diskusi panjang kita sepakat memakai FastAPI untuk backend."]


def test_analysis_unavailable_keeps_transcript_usable(client, services):
    class Down:
        name = "ollama"

        def info(self):
            return {"name": "ollama", "available": False, "reason": "Server Ollama tidak dapat dihubungi."}

    services.intelligence = Down()
    mid, _ = _seed_meeting(services, [("Rina", "Kita sepakat.")])
    job = client.post(f"/api/meetings/{mid}/analyze").json()
    drain(services)
    j = client.get(f"/api/jobs/{job['id']}").json()
    assert j["status"] == "failed" and "tidak tersedia" in j["error"]
    d = client.get(f"/api/meetings/{mid}").json()
    assert d["status"] == "ready" and d["segments"] and d["insights"] == []


def test_delete_meeting_removes_files(client, services, tmp_path):
    m = _upload(client, corpus.make_tone(tmp_path / "a.wav", 3)).json()
    drain(services)
    root = services.storage.derived_root(m["id"])
    assert root.exists() and services.storage.find_upload(m["id"])
    assert client.delete(f"/api/meetings/{m['id']}").status_code == 200
    assert not root.exists() and services.storage.find_upload(m["id"]) is None
    assert client.get(f"/api/meetings/{m['id']}").status_code == 404
    assert client.get(f"/api/meetings/{m['id']}/audio").status_code == 404
    assert services.db.one("SELECT COUNT(*) n FROM segments WHERE meeting_id=?", (m["id"],))["n"] == 0
    assert json.loads(json.dumps(client.get("/api/meetings").json())) == []
