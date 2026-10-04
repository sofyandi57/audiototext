"""Evaluation metrics: WER/CER and key-term accuracy for Indonesian transcripts."""

from __future__ import annotations

import re
import unicodedata


def normalize(text: str) -> list[str]:
    """Lowercase, strip punctuation (keeps digits and intra-word hyphens)."""
    t = unicodedata.normalize("NFKC", text).lower()
    t = re.sub(r"[^\w\s-]", " ", t)
    t = re.sub(r"(?<!\w)-|-(?!\w)", " ", t)
    return t.split()


def edit_distance(ref: list, hyp: list) -> tuple[int, int, int, int]:
    """Levenshtein alignment. Returns (distance, substitutions, deletions, insertions)."""
    n, m = len(ref), len(hyp)
    # each cell: (cost, subs, dels, ins)
    prev = [(j, 0, 0, j) for j in range(m + 1)]
    for i in range(1, n + 1):
        cur = [(i, 0, i, 0)] + [None] * m  # type: ignore[list-item]
        for j in range(1, m + 1):
            if ref[i - 1] == hyp[j - 1]:
                cur[j] = prev[j - 1]
                continue
            sub, dele, ins = prev[j - 1], prev[j], cur[j - 1]
            best = min(sub, dele, ins, key=lambda c: c[0])
            if best is sub:
                cur[j] = (sub[0] + 1, sub[1] + 1, sub[2], sub[3])
            elif best is dele:
                cur[j] = (dele[0] + 1, dele[1], dele[2] + 1, dele[3])
            else:
                cur[j] = (ins[0] + 1, ins[1], ins[2], ins[3] + 1)
        prev = cur
    return prev[m]


def wer(reference: str, hypothesis: str) -> dict:
    ref, hyp = normalize(reference), normalize(hypothesis)
    dist, s, d, i = edit_distance(ref, hyp)
    return {"wer": dist / max(len(ref), 1), "substitutions": s, "deletions": d, "insertions": i,
            "ref_words": len(ref)}


def cer(reference: str, hypothesis: str) -> float:
    ref = list(" ".join(normalize(reference)))
    hyp = list(" ".join(normalize(hypothesis)))
    return edit_distance(ref, hyp)[0] / max(len(ref), 1)


def term_accuracy(terms: list[str], hypothesis: str) -> dict:
    """Share of key terms (names, numbers, acronyms, jargon) found verbatim."""
    hyp = " " + " ".join(normalize(hypothesis)) + " "
    found = [t for t in terms if " " + " ".join(normalize(t)) + " " in hyp]
    return {"accuracy": len(found) / max(len(terms), 1), "found": found,
            "missed": [t for t in terms if t not in found]}


def token_recall(reference: str, extracted: str) -> float:
    """Multiset recall of reference tokens in extracted text (PDF completeness)."""
    from collections import Counter

    ref, ext = Counter(normalize(reference)), Counter(normalize(extracted))
    total = sum(ref.values())
    return sum(min(c, ext[w]) for w, c in ref.items()) / max(total, 1)
