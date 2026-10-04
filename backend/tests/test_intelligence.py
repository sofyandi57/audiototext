from __future__ import annotations

import json

from app.intelligence import OllamaEngine, RulesEngine, run_analysis
from app.intelligence.provenance import Item, validate
from app.intelligence.rules import find_deadline, find_owner


def seg(i, text, speaker=None):
    return {"id": f"s{i}", "start": i * 10.0, "end": i * 10.0 + 9, "text": text, "speaker": speaker}


def test_small_talk_produces_no_decisions_or_actions():
    segs = [seg(1, "Selamat pagi semua."), seg(2, "Cuacanya cerah sekali hari ini ya."),
            seg(3, "Iya, tadi macet sedikit di jalan.")]
    kinds = {i.kind for i in run_analysis(RulesEngine(), segs).items}
    assert "decision" not in kinds and "action" not in kinds


def test_undecided_is_question_not_decision():
    items = run_analysis(RulesEngine(), [seg(1, "Soal hosting belum diputuskan.")]).items
    assert [i.kind for i in items] == ["question"]


def test_owner_and_deadline_extraction():
    assert find_owner("Tolong Budi siapkan dokumen.") == "Budi"
    assert find_owner("Tim backend akan memperbaiki bug login.") == "Tim backend"
    assert find_owner("PIC-nya Sari untuk desain.") == "Sari"
    assert find_owner("PIC: Sari untuk desain.") == "Sari"
    assert find_owner("Tolong siapkan dokumen.") is None  # no name => none, never guessed
    assert find_deadline("kirim paling lambat 15 Oktober") == "paling lambat 15 Oktober"
    assert find_deadline("selesaikan sebelum akhir bulan ini") == "sebelum akhir bulan ini"
    assert find_deadline("rapat hari Senin kemarin menyenangkan") is None  # weekday w/o cue


def test_validator_rejects_unreferenced_and_fabricated_fields():
    segments = {s["id"]: s for s in [seg(1, "Tolong kirim laporan.", "Rina")]}
    res = validate([
        Item("action", "Kirim laporan", ["s1"], owner="Budi", deadline="besok"),
        Item("decision", "Kita pindah ke AWS", ["s999"]),
        Item("decision", "Tanpa sumber", []),
    ], segments)
    assert len(res.items) == 1 and len(res.rejected) == 2
    a = res.items[0]
    assert a.owner is None and not a.owner_confirmed  # Budi never mentioned
    assert a.deadline is None and not a.deadline_confirmed  # "besok" never said
    assert (a.start, a.end) == (10.0, 19.0)


def test_validator_accepts_speaker_owner_only_for_first_person():
    segments = {s["id"]: s for s in [seg(1, "Saya akan cek servernya.", "Sari"), seg(2, "Server perlu dicek.", "Sari")]}
    res = validate([Item("action", "cek", ["s1"], owner="Sari"), Item("action", "cek", ["s2"], owner="Sari")], segments)
    assert res.items[0].owner_confirmed is True
    assert res.items[1].owner is None


def test_llm_engine_output_goes_through_validator(monkeypatch):
    eng = OllamaEngine("http://localhost:1", "tiny")
    fake = {"items": [
        {"kind": "decision", "text": "Pakai SQLite", "segment_ids": ["s1"], "owner": None, "deadline": None},
        {"kind": "action", "text": "Budi deploy", "segment_ids": ["s1"], "owner": "Budi", "deadline": "Senin"},
        {"kind": "decision", "text": "Halusinasi", "segment_ids": ["s42"]},
        {"kind": "bogus", "text": "x", "segment_ids": ["s1"]},
    ]}
    monkeypatch.setattr(eng, "_call", lambda prompt: json.dumps(fake))
    res = run_analysis(eng, [seg(1, "Kita sepakat pakai SQLite.")])
    assert [i.text for i in res.items] == ["Pakai SQLite", "Budi deploy"]
    assert res.items[1].owner is None and res.items[1].deadline is None
    assert len(res.rejected) == 1


def test_llm_garbage_output_yields_nothing(monkeypatch):
    eng = OllamaEngine("http://localhost:1", "tiny")
    monkeypatch.setattr(eng, "_call", lambda prompt: "maaf saya tidak bisa")
    assert run_analysis(eng, [seg(1, "x")]).items == []


def test_ollama_unconfigured_reports_unavailable():
    assert OllamaEngine("", "").info()["available"] is False


def test_summary_is_extractive_and_chronological():
    texts = [
        "Kita membahas arsitektur aplikasi transkripsi rapat untuk tim produk.",
        "Arsitektur aplikasi memakai FastAPI dan worker terpisah untuk transkripsi.",
        "Oke.",
        "Kita sepakat worker transkripsi berjalan di CPU tanpa GPU.",
        "Tim produk meminta ekspor transkripsi ke Markdown.",
    ]
    segs = [seg(i, t) for i, t in enumerate(texts)]
    summary = [i for i in run_analysis(RulesEngine(), segs).items if i.kind == "summary"]
    assert summary and all(i.text in texts for i in summary)
    assert [i.start for i in summary] == sorted(i.start for i in summary)
    assert "Oke." not in [i.text for i in summary]
