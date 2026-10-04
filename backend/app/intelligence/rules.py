"""Deterministic, rule-based meeting analysis for Bahasa Indonesia.

It never generates new sentences: every item is a sentence quoted from the
transcript, classified by keyword patterns. The summary is extractive.
This keeps it honest (no invented decisions) at the cost of recall and
fluency; a local LLM engine can be plugged in behind the same validator.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from .provenance import Item

_W = r"(?<!\w)"
_E = r"(?!\w)"

DECISION = re.compile(
    _W + r"(diputuskan|memutuskan|putuskan|disepakati|sepakat|menyepakati|kesepakatan(?:nya)?|"
    r"keputusan(?:nya)?|setuju untuk|kita setuju|final(?:nya)?|fix(?:nya)? (?:pakai|pilih)|"
    r"jadi kita (?:pakai|pilih|gunakan|lanjut)|decided|agreed)" + _E, re.I)
NOT_DECIDED = re.compile(_W + r"(belum|tidak|nggak|gak) (di)?(putuskan|sepakat|disepakati|final)" + _E, re.I)
ACTION = re.compile(
    _W + r"(tolong|mohon|harap|silakan|(?:saya|aku|kami|kita|dia|beliau|\w+) akan|nanti \w+ (?:yang )?"
    r"(?:siapkan|kirim|buat|cek|urus|kerjakan)|bertanggung jawab|ditugaskan|pic(?:nya)?|"
    r"action item|tindak lanjut|follow[ -]?up|to[ -]?do|tugas(?:nya)?|"
    r"(?:perlu|harus|wajib) (?:segera )?(?:di\w{3,}|siapkan|kirim|buat|cek|update|perbaiki|selesaikan|kerjakan)\w*)" + _E,
    re.I)
RISK = re.compile(
    _W + r"(risiko(?:nya)?|resiko(?:nya)?|berisiko|bahaya|kendala|hambatan|terlambat|telat|delay|blocker|bottleneck|"
    r"khawatir|kekhawatiran|bisa gagal|tidak cukup|kurang (?:dana|anggaran|orang|waktu)|"
    r"over ?budget|melebihi anggaran|bug|downtime)" + _E, re.I)
OPEN_Q = re.compile(
    _W + r"(belum (?:jelas|pasti|diputuskan|tahu|ada keputusan)|masih (?:dibahas|terbuka|dipertimbangkan)|"
    r"perlu (?:dicek|dikonfirmasi|konfirmasi|didiskusikan)|apakah|bagaimana kalau|gimana kalau)" + _E,
    re.I)

NOT_NAMES = {
    "tolong", "mohon", "saya", "aku", "kami", "kita", "nanti", "jadi", "oke", "ok", "ini", "itu",
    "dia", "beliau", "harap", "silakan", "kalau", "terus", "lalu", "dan", "yang", "baik", "ya",
    "untuk", "sudah", "belum", "mungkin", "apakah", "semua", "mereka", "anda", "kamu", "bapak", "ibu",
    "pak", "bu", "mas", "mbak", "sebelum", "setelah", "minggu", "senin", "selasa", "rabu", "kamis",
    "jumat", "sabtu", "besok", "hari",
}
_NAME = r"(?P<owner>(?:[Tt]im \w+)|(?:(?:[Pp]ak|[Bb]u|[Mm]as|[Mm]bak) [A-Z]\w+)|[A-Z][a-z]+)"
OWNER_PATTERNS = [
    re.compile(r"(?i:tolong|mohon|minta)\s+" + _NAME + r"\b"),
    re.compile(_NAME + r"\s+(?:yang\s+)?(?:akan|bertanggung jawab|siap|bisa)\b"),
    re.compile(r"(?:PIC|pic)(?:-?nya)?\s*(?:adalah|:|=)?\s*" + _NAME),
    re.compile(r"(?:ditugaskan|diserahkan)\s+(?:ke|kepada)\s+" + _NAME),
]
_MONTHS = r"(?:januari|februari|maret|april|mei|juni|juli|agustus|september|oktober|november|desember)"
_DAYS = r"(?:senin|selasa|rabu|kamis|jumat|jum'at|sabtu|minggu)"
DEADLINE = re.compile(
    r"(?:(?:paling lambat|sebelum|deadline(?:nya)?|tenggat(?: waktu)?|batas waktu|maksimal|"
    r"target(?:nya)?|selesai|by)\s+)?"
    r"(?P<when>hari ini|besok|lusa|minggu depan|bulan depan|"
    r"akhir (?:minggu|bulan|tahun|kuartal)(?: ini| depan)?|"
    r"(?:hari )?" + _DAYS + r"(?: depan| ini)?|"
    r"tanggal \d{1,2}(?: " + _MONTHS + r")?(?: \d{4})?|\d{1,2} " + _MONTHS + r"(?: \d{4})?|"
    r"\d{1,2}/\d{1,2}(?:/\d{2,4})?|(?:jam|pukul) \d{1,2}(?:[.:]\d{2})?)",
    re.I)
_DEADLINE_CUE = re.compile(r"(paling lambat|sebelum|deadline|tenggat|batas waktu|maksimal|target|selesai|by)\s*$", re.I)

STOPWORDS = set(
    "yang dan di ke dari ini itu untuk dengan pada adalah juga akan sudah belum tidak ya kita kami saya "
    "aku kamu anda dia mereka oke ok jadi terus lalu nah eh hmm em ehm iya kan sih dong deh lah kok "
    "atau tapi tetapi karena kalau jika bisa ada dalam sebagai oleh lebih sangat masih harus perlu "
    "nanti sama seperti saja aja gitu begitu gimana bagaimana apa siapa kapan dimana mana the a to of "
    "and is in it that this we i you be will for on".split()
)
FILLER = re.compile(r"^(oke|ok|ya|iya|baik|hmm+|eh+|em+|sip|siap|betul|benar)[.!?,\s]*$", re.I)


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def find_owner(sentence: str) -> str | None:
    for pat in OWNER_PATTERNS:
        for m in pat.finditer(sentence):
            name = m.group("owner").strip()
            if name.split()[0].lower() in NOT_NAMES and not name.lower().startswith("tim "):
                continue
            return name
    return None


def find_deadline(sentence: str) -> str | None:
    for m in DEADLINE.finditer(sentence):
        phrase = m.group(0).strip()
        when = m.group("when")
        # A bare weekday/"minggu" is only a deadline when preceded by a cue word.
        has_cue = phrase.lower() != when.lower() or _DEADLINE_CUE.search(sentence[: m.start()])
        bare_ambiguous = re.fullmatch(r"(?:hari )?" + _DAYS, when, re.I) is not None
        if bare_ambiguous and not has_cue:
            continue
        return phrase
    return None


def analyze(segments: list[dict], max_summary: int = 6) -> list[Item]:
    """``segments``: dicts with id, start, end, text, speaker (ordered by time)."""
    items: list[Item] = []
    candidates: list[tuple[str, str]] = []  # (segment_id, sentence)
    for seg in segments:
        for sent in split_sentences(seg["text"]):
            candidates.append((seg["id"], sent))
            is_q = sent.endswith("?")
            if DECISION.search(sent) and not NOT_DECIDED.search(sent) and not is_q:
                items.append(Item("decision", sent, [seg["id"]]))
            if ACTION.search(sent) and not is_q:
                owner = find_owner(sent)
                if not owner and re.search(r"\b(saya|aku)\s+(akan|siap|yang)\b", sent, re.I) and seg.get("speaker"):
                    owner = seg["speaker"]
                items.append(Item("action", sent, [seg["id"]], owner=owner, deadline=find_deadline(sent)))
            if RISK.search(sent):
                items.append(Item("risk", sent, [seg["id"]]))
            if is_q or OPEN_Q.search(sent) or NOT_DECIDED.search(sent):
                items.append(Item("question", sent, [seg["id"]]))
    items += _extractive_summary(candidates, max_summary)
    return items


def _tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-zA-Z0-9]+", text.lower()) if w not in STOPWORDS and len(w) > 2]


def _extractive_summary(candidates: list[tuple[str, str]], max_items: int) -> list[Item]:
    usable = [(i, sid, s) for i, (sid, s) in enumerate(candidates)
              if len(s.split()) >= 6 and not FILLER.match(s)]
    if not usable:
        return []
    freq = Counter(t for _, _, s in usable for t in set(_tokens(s)))
    n_docs = len(usable)

    def score(sent: str) -> float:
        toks = _tokens(sent)
        if not toks:
            return 0.0
        base = sum(math.log(1 + freq[t]) for t in set(toks)) / math.sqrt(len(toks))
        if DECISION.search(sent):
            base *= 1.5
        if ACTION.search(sent):
            base *= 1.2
        return base

    k = max(1, min(max_items, round(n_docs / 6) or 1))
    best = sorted(usable, key=lambda x: score(x[2]), reverse=True)[:k]
    best.sort(key=lambda x: x[0])  # chronological
    return [Item("summary", s, [sid]) for _, sid, s in best]
