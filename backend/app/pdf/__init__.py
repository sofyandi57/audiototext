"""PDF pipeline: extract -> clean -> structure into sections."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .chapters import apply_toc, build_sections
from .clean import body_font_size, build_elements, clean_pages
from .extract import PdfError, extract
from .ocr import TesseractOCR
from .types import Page, Section

__all__ = ["PdfError", "TesseractOCR", "ProcessedDocument", "process_pdf"]


@dataclass
class ProcessedDocument:
    pages: list[Page]
    sections: list[Section]
    report: dict


def process_pdf(
    path: Path,
    ocr: TesseractOCR | None,
    min_page_chars: int = 25,
    section_max_chars: int = 6000,
    max_pages: int | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> ProcessedDocument:
    raw = extract(path, ocr, min_page_chars=min_page_chars, max_pages=max_pages, progress=progress)
    report = clean_pages(raw.pages)
    body = body_font_size(raw.pages)
    elements = build_elements(raw.pages, body, report)
    elements = apply_toc(elements, raw.toc)
    sections = build_sections(elements, raw.pages, section_max_chars)
    report["used_outline"] = bool(raw.toc)
    report["ocr_pages"] = [p.page_no for p in raw.pages if p.text_source == "ocr"]
    report["review_pages"] = [
        {"page": p.page_no, "reason": p.review_reason} for p in raw.pages if p.needs_review
    ]
    if not any(s.paragraphs for s in sections):
        if report["review_pages"]:
            report["warning"] = "Tidak ada teks yang dapat diekstrak. Periksa halaman yang ditandai."
        else:
            raise PdfError("Tidak ada teks yang dapat diekstrak dari PDF ini.")
    return ProcessedDocument(raw.pages, sections, report)
