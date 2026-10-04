from app.evaluation import cer, term_accuracy, token_recall, wer


def test_wer_counts_operations():
    r = wer("kita sepakat memakai FastAPI", "kita sepakat pakai fast api")
    # memakai->pakai (S), FastAPI->fast (S), +api (I)
    assert (r["substitutions"], r["deletions"], r["insertions"]) == (2, 0, 1)
    assert r["wer"] == 3 / 4


def test_wer_ignores_case_and_punctuation_keeps_reduplication():
    assert wer("Anak-anak, BERMAIN!", "anak-anak bermain")["wer"] == 0
    assert wer("anak-anak", "anak anak")["wer"] == 2.0  # 1 sub + 1 ins: hyphenation matters


def test_wer_empty_hypothesis():
    assert wer("satu dua tiga", "")["deletions"] == 3


def test_cer():
    assert cer("abc", "abc") == 0
    assert round(cer("rapat", "rapit"), 2) == 0.2


def test_term_accuracy():
    r = term_accuracy(["FastAPI", "Rp 1.500.000", "Bu Rina"], "tolong bu rina cek fastapi")
    assert r["found"] == ["FastAPI", "Bu Rina"] and r["missed"] == ["Rp 1.500.000"]


def test_token_recall():
    assert token_recall("a b c d", "a b c d e") == 1.0
    assert token_recall("a b c d", "a b") == 0.5
