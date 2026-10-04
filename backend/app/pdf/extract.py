"""PDF text extraction with reading order, low-text detection and OCR fallback."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pymupdf as fitz

from .ocr import TesseractOCR
from .types import Block, Line, Page

log = logging.getLogger(__name__)


class PdfError(Exception):
    """User-facing extraction failure (malformed, encrypted, empty...)."""


@dataclass
class RawDocument:
    pages: list[Page]
    toc: list[tuple[int, str, int]]  # (level, title, page_no)


def open_pdf(path: Path) -> fitz.Document:
    try:
        doc = fitz.open(path, filetype="pdf")
    except Exception as exc:  # fitz raises several types for broken files
        raise PdfError("File PDF rusak atau bukan PDF yang valid.") from exc
    if doc.needs_pass:
        doc.close()
        raise PdfError("PDF dilindungi kata sandi. Buka kuncinya terlebih dahulu lalu unggah ulang.")
    if doc.page_count == 0:
        doc.close()
        raise PdfError("PDF tidak memiliki halaman yang bisa dibaca (file mungkin rusak).")
    return doc


def _page_lines(page, page_no: int) -> list[Block]:
    data = page.get_text("dict", flags=fitz.TEXT_PRESERVE_LIGATURES | fitz.TEXT_MEDIABOX_CLIP)
    blocks: list[Block] = []
    for b in data.get("blocks", []):
        if b.get("type") != 0:
            continue
        lines: list[Line] = []
        for ln in b.get("lines", []):
            spans = [s for s in ln.get("spans", []) if s.get("text", "").strip()]
            if not spans:
                continue
            text = "".join(s["text"] for s in ln["spans"]).strip()
            size = max(s["size"] for s in spans)
            bold = all((s["flags"] & 16) or "bold" in s["font"].lower() for s in spans)
            x0, y0, x1, y1 = ln["bbox"]
            lines.append(Line(" ".join(text.split()), x0, y0, x1, y1, round(size, 1), bold, page_no))
        if lines:
            blocks.append(Block(lines, page_no))
    return blocks


def order_blocks(blocks: list[Block], width: float) -> list[Block]:
    """Order blocks for reading. Handles simple two-column layouts.

    Full-width blocks split the page into vertical bands; inside a band the
    left column is read before the right column.
    """
    if not blocks:
        return []
    mid = width / 2
    gutter = width * 0.05

    def side(b: Block) -> str:
        if b.x1 <= mid + gutter:
            return "L"
        if b.x0 >= mid - gutter:
            return "R"
        return "F"

    sides = [side(b) for b in blocks]
    lefts = [b for b, s in zip(blocks, sides) if s == "L"]
    rights = [b for b, s in zip(blocks, sides) if s == "R"]
    two_col = False
    if len(lefts) >= 1 and len(rights) >= 1:
        # Columns must overlap vertically to count as a two-column layout.
        for l in lefts:
            if any(r.y0 < l.y1 and l.y0 < r.y1 for r in rights):
                two_col = True
                break
    if not two_col:
        return sorted(blocks, key=lambda b: (round(b.y0, 0), b.x0))

    ordered: list[Block] = []
    full = sorted([b for b, s in zip(blocks, sides) if s == "F"], key=lambda b: b.y0)
    band_top = -1e9
    for fb in full + [None]:
        band_bottom = fb.y0 if fb else 1e9
        band = [b for b, s in zip(blocks, sides) if s != "F" and band_top <= b.y0 < band_bottom]
        ordered += sorted([b for b in band if side(b) == "L"], key=lambda b: b.y0)
        ordered += sorted([b for b in band if side(b) == "R"], key=lambda b: b.y0)
        if fb:
            ordered.append(fb)
            band_top = fb.y0
    return ordered


def extract(
    path: Path,
    ocr: TesseractOCR | None,
    min_page_chars: int = 25,
    max_pages: int | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> RawDocument:
    doc = open_pdf(path)
    try:
        if max_pages and doc.page_count > max_pages:
            raise PdfError(f"PDF memiliki {doc.page_count} halaman; batas saat ini {max_pages}.")
        pages: list[Page] = []
        for i in range(doc.page_count):
            page_no = i + 1
            try:
                page = doc.load_page(i)
                blocks = _page_lines(page, page_no)
                has_images = bool(page.get_images(full=False))
            except Exception:  # damaged page objects; keep going, flag it
                log.exception("failed to parse page %s", page_no)
                pages.append(Page(page_no, 595, 842, [], "none", False, True,
                                  "Halaman rusak dan tidak bisa dibaca."))
                continue
            width, height = page.rect.width, page.rect.height
            p = Page(page_no, width, height, order_blocks(blocks, width), "text", has_images)
            if p.char_count < min_page_chars:
                _handle_low_text(p, page, ocr, min_page_chars)
            pages.append(p)
            if progress:
                progress(page_no, doc.page_count)
        toc = [(lvl, title.strip(), pg) for lvl, title, pg in doc.get_toc(simple=True) if title.strip()]
        return RawDocument(pages, toc)
    finally:
        doc.close()


def _handle_low_text(p: Page, page, ocr: TesseractOCR | None, min_chars: int) -> None:
    if not p.has_images and p.char_count == 0:
        p.text_source = "none"
        p.needs_review = True
        p.review_reason = "Halaman kosong (tidak ada teks maupun gambar)."
        return
    if ocr is None or not ocr.available():
        p.needs_review = True
        p.review_reason = (
            "Halaman tampak hasil pindaian / minim teks, dan OCR tidak tersedia di server. "
            "Periksa atau ketik ulang isinya."
        )
        if p.char_count == 0:
            p.text_source = "none"
        return
    try:
        result = ocr.ocr_page(page, p.page_no)
    except Exception:
        log.exception("OCR failed on page %s", p.page_no)
        p.needs_review = True
        p.review_reason = "OCR gagal pada halaman ini. Periksa isinya secara manual."
        return
    ocr_chars = sum(len(l.text) for b in result.blocks for l in b.lines)
    if ocr_chars > p.char_count:
        p.blocks = order_blocks(result.blocks, p.width)
        p.text_source = "ocr"
        p.ocr_confidence = round(result.mean_confidence, 1)
    if p.char_count < min_chars:
        p.needs_review = True
        p.review_reason = "OCR hampir tidak menemukan teks pada halaman ini."
    elif p.text_source == "ocr" and result.mean_confidence < 70:
        p.needs_review = True
        p.review_reason = f"Hasil OCR berkeyakinan rendah ({result.mean_confidence:.0f}%). Mohon periksa."
