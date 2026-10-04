"""Group elements into ordered chapters/sections of bounded size."""

from __future__ import annotations

import re

from .types import Element, Page, Section


def _norm(t: str) -> str:
    return re.sub(r"[^\w]+", " ", t.lower()).strip()


def apply_toc(elements: list[Element], toc: list[tuple[int, str, int]]) -> list[Element]:
    """Use the PDF outline (bookmarks) as the authoritative chapter list.

    Existing heading guesses are demoted to paragraphs only when an outline
    exists, then each outline entry is matched to the first element on its
    page that starts with the entry title. Unmatched entries are inserted at
    the start of their page so ordering is preserved.
    """
    if not toc:
        return elements
    max_level = 2
    out = [Element("paragraph", e.text, e.page_no, e.level) for e in elements]
    for level, title, page_no in toc:
        if level > max_level:
            continue
        nt = _norm(title)
        match = None
        for e in out:
            if e.page_no in (page_no, page_no + 1) and _norm(e.text).startswith(nt):
                match = e
                break
        if match:
            if len(_norm(match.text)) <= len(nt) + 3:
                match.kind, match.level, match.text = "heading", level, title
            else:  # title glued to body text: split it off
                rest = match.text[len(title):].strip() if match.text.startswith(title) else match.text
                idx = out.index(match)
                match.text = rest
                out.insert(idx, Element("heading", title, page_no, level))
        else:
            idx = next((i for i, e in enumerate(out) if e.page_no >= page_no), len(out))
            out.insert(idx, Element("heading", title, page_no, level))
    return out


def build_sections(elements: list[Element], pages: list[Page], max_chars: int) -> list[Section]:
    review_pages = {p.page_no for p in pages if p.needs_review}
    sections: list[Section] = []
    current: Section | None = None

    def start(title: str, level: int, page_no: int) -> Section:
        s = Section(title=title, level=level, start_page=page_no, end_page=page_no)
        sections.append(s)
        return s

    for el in elements:
        if el.kind == "heading":
            # Consecutive headings (e.g. "BAB I" + "PENDAHULUAN") form one title.
            if current and not current.paragraphs and current.start_page == el.page_no:
                current.title = f"{current.title} — {el.text}"
                continue
            current = start(el.text, el.level, el.page_no)
            continue
        if current is None:
            current = start("Awal dokumen", 1, el.page_no)
        current.paragraphs.append(el.text)
        current.end_page = el.end_page or el.page_no

    # Pages with no extractable text still need to be visible for review.
    for p in pages:
        if p.needs_review and not any(
            s.start_page is not None and s.start_page <= p.page_no <= (s.end_page or s.start_page)
            for s in sections
        ):
            s = Section(title=f"Halaman {p.page_no} (perlu ditinjau)", level=1,
                        start_page=p.page_no, end_page=p.page_no, needs_review=True)
            idx = next((i for i, x in enumerate(sections) if (x.start_page or 0) > p.page_no), len(sections))
            sections.insert(idx, s)

    # Drop heading-only sections that have no content and no review flag.
    sections = [s for s in sections if s.paragraphs or s.needs_review]

    for s in sections:
        if s.start_page is not None:
            rng = range(s.start_page, (s.end_page or s.start_page) + 1)
            if any(pg in review_pages for pg in rng):
                s.needs_review = True

    return split_long(sections, max_chars)


def split_long(sections: list[Section], max_chars: int) -> list[Section]:
    out: list[Section] = []
    for s in sections:
        if len(s.text) <= max_chars:
            out.append(s)
            continue
        parts: list[list[str]] = [[]]
        size = 0
        for para in _split_paragraphs(s.paragraphs, max_chars):
            if size + len(para) > max_chars and parts[-1]:
                parts.append([])
                size = 0
            parts[-1].append(para)
            size += len(para) + 2
        for i, paras in enumerate(parts, start=1):
            out.append(Section(
                title=s.title if i == 1 else f"{s.title} (bagian {i})", level=s.level,
                paragraphs=paras, start_page=s.start_page, end_page=s.end_page,
                needs_review=s.needs_review,
            ))
    return out


def _split_paragraphs(paragraphs: list[str], max_chars: int) -> list[str]:
    """Break single paragraphs that are themselves longer than max_chars at sentence ends."""
    out = []
    for p in paragraphs:
        if len(p) <= max_chars:
            out.append(p)
            continue
        buf = ""
        for sent in re.split(r"(?<=[.!?])\s+", p):
            if buf and len(buf) + len(sent) + 1 > max_chars:
                out.append(buf)
                buf = sent
            else:
                buf = f"{buf} {sent}".strip()
        if buf:
            out.append(buf)
    return out
