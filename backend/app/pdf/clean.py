"""Remove repeated headers/footers and page numbers; repair line wrapping.

Every removal is recorded in a report so the user can see (and restore by
editing) what was dropped. Only short lines inside the top/bottom margin bands
are ever candidates, so body text is never removed by these rules.
"""

from __future__ import annotations

import re
from collections import defaultdict

from .types import Block, Element, Page

MARGIN_FRACTION = 0.1
MAX_HEADER_LEN = 120

_PAGE_NUM = re.compile(
    r"^(?:(?:hal(?:aman)?|page|p)\.?\s*)?[-–—(\[]?\s*(\d{1,4}|[ivxlcdm]{1,7})\s*[-–—)\]]?"
    r"(?:\s*(?:dari|of|/)\s*\d{1,4})?$",
    re.IGNORECASE,
)
_SENTENCE_END = re.compile(r"[.!?:;\"”’)]$")


def _zone(line, page: Page) -> str | None:
    if line.y1 <= page.height * MARGIN_FRACTION:
        return "top"
    if line.y0 >= page.height * (1 - MARGIN_FRACTION):
        return "bottom"
    return None


def _norm(text: str) -> str:
    t = re.sub(r"\d+", "#", text.lower())
    return re.sub(r"\s+", " ", t).strip()


def is_page_number(text: str) -> bool:
    return bool(_PAGE_NUM.match(text.strip()))


def clean_pages(pages: list[Page]) -> dict:
    """Mutates pages in place. Returns a JSON-serialisable cleaning report."""
    text_pages = [p for p in pages if p.blocks]
    counts: dict[tuple[str, str], set[int]] = defaultdict(set)
    for p in text_pages:
        for b in p.blocks:
            for ln in b.lines:
                zone = _zone(ln, p)
                if zone and len(ln.text) <= MAX_HEADER_LEN:
                    counts[(zone, _norm(ln.text))].add(p.page_no)

    n = len(text_pages)
    min_repeats = max(2, int(round(n * 0.4)))
    repeated = {k for k, v in counts.items() if len(v) >= min_repeats and k[1]}

    removed: list[dict] = []
    for p in text_pages:
        new_blocks: list[Block] = []
        for b in p.blocks:
            kept = []
            for ln in b.lines:
                zone = _zone(ln, p)
                reason = None
                if zone and is_page_number(ln.text):
                    reason = "page_number"
                elif zone and (zone, _norm(ln.text)) in repeated:
                    reason = "header" if zone == "top" else "footer"
                if reason:
                    removed.append({"page": p.page_no, "text": ln.text, "reason": reason})
                else:
                    kept.append(ln)
            if kept:
                b.lines = kept
                new_blocks.append(b)
        p.blocks = new_blocks

    summary: dict[str, int] = defaultdict(int)
    for r in removed:
        summary[r["reason"]] += 1
    return {"removed": removed, "summary": dict(summary), "dehyphenated": 0, "merged_across_pages": 0}


def join_lines(lines: list[str], report: dict | None = None) -> str:
    """Join wrapped lines into a paragraph, repairing end-of-line hyphenation.

    Indonesian reduplication ("anak-anak") is kept: a hyphen is only dropped
    when the fragments differ and the continuation starts in lowercase.
    """
    out = ""
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if not out:
            out = line
            continue
        m = re.search(r"(\w+)-$", out)
        if m and line[:1].islower():
            first = m.group(1)
            nxt = re.match(r"\w+", line)
            if nxt and nxt.group(0).lower().startswith(first.lower()):
                out = out + line  # reduplication split at the hyphen: keep "anak-anak"
            else:
                out = out[:-1] + line
                if report is not None:
                    report["dehyphenated"] = report.get("dehyphenated", 0) + 1
        else:
            out = out + " " + line
    return out


def build_elements(pages: list[Page], body_size: float, report: dict) -> list[Element]:
    """Turn ordered blocks into heading/paragraph elements."""
    elements: list[Element] = []
    heading_sizes = sorted(
        {round(l.size) for p in pages for b in p.blocks for l in b.lines if l.size >= body_size * 1.2},
        reverse=True,
    )

    def heading_level(block: Block) -> int | None:
        text = block.text.strip()
        if len(text) > 150 or len(block.lines) > 3 or _SENTENCE_END.search(text) and not re.match(
            r"^(bab|chapter|bagian)\b", text, re.I
        ):
            return None
        if re.match(r"^(bab|chapter|bagian)\s+([ivxlcdm]+|\d+)\b", text, re.I):
            return 1
        size = max(l.size for l in block.lines)
        if size >= body_size * 1.2:
            r = round(size)
            return min(heading_sizes.index(r) + 1, 3) if r in heading_sizes else 2
        if all(l.bold for l in block.lines) and len(text) <= 80 and not text.endswith(","):
            return min(len(heading_sizes) + 1, 3)
        return None

    for p in pages:
        for b in p.blocks:
            level = heading_level(b)
            if level:
                elements.append(Element("heading", " ".join(b.text.split()), p.page_no, level))
            else:
                text = join_lines([l.text for l in b.lines], report)
                if text:
                    elements.append(Element("paragraph", text, p.page_no))

    # Merge paragraphs split by a page break (or column break): previous one has
    # no sentence-ending punctuation and the next starts lowercase.
    merged: list[Element] = []
    for el in elements:
        prev = merged[-1] if merged else None
        if (
            prev and prev.kind == "paragraph" and el.kind == "paragraph"
            and not _SENTENCE_END.search(prev.text) and el.text[:1].islower()
        ):
            if el.page_no != (prev.end_page or prev.page_no):
                report["merged_across_pages"] = report.get("merged_across_pages", 0) + 1
            prev.end_page = el.end_page or el.page_no
            prev.text = join_lines([prev.text, el.text], report)
        else:
            merged.append(el)
    return merged


def body_font_size(pages: list[Page]) -> float:
    weights: dict[float, int] = defaultdict(int)
    for p in pages:
        for b in p.blocks:
            for l in b.lines:
                weights[round(l.size, 0)] += len(l.text)
    if not weights:
        return 11.0
    return max(weights.items(), key=lambda kv: kv[1])[0]
