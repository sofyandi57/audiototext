from __future__ import annotations

import pymupdf
import pytest

from app.pdf import PdfError, TesseractOCR, process_pdf
from app.pdf.chapters import split_long
from app.pdf.clean import is_page_number, join_lines
from app.pdf.types import Section

from . import corpus
from .conftest import requires_tesseract


def test_chapters_in_order_with_pages(tmp_path):
    doc = process_pdf(corpus.make_book_pdf(tmp_path / "b.pdf"), ocr=None)
    titles = [s.title for s in doc.sections]
    assert titles == ["BAB I PENDAHULUAN", "BAB II METODOLOGI", "BAB III HASIL"]
    assert [s.start_page for s in doc.sections] == [1, 2, 3]
    assert not any(s.needs_review for s in doc.sections)


def test_outline_is_used_for_chapters(tmp_path):
    doc = process_pdf(corpus.make_book_pdf(tmp_path / "b.pdf", with_outline=True), ocr=None)
    assert doc.report["used_outline"] is True
    assert [s.title for s in doc.sections] == [c[0] for c in corpus.CHAPTERS]


def test_repeated_header_and_page_numbers_removed_and_reported(tmp_path):
    doc = process_pdf(corpus.make_book_pdf(tmp_path / "b.pdf"), ocr=None)
    full = "\n".join(s.text for s in doc.sections)
    assert corpus.HEADER not in full
    assert "Halaman 1 dari 3" not in full
    assert doc.report["summary"] == {"header": 3, "page_number": 3}
    removed = {(r["page"], r["reason"]) for r in doc.report["removed"]}
    assert (2, "header") in removed and (3, "page_number") in removed


def test_no_substantive_content_lost(tmp_path):
    doc = process_pdf(corpus.make_book_pdf(tmp_path / "b.pdf"), ocr=None)
    full = " ".join(s.text for s in doc.sections)
    for _, paras in corpus.CHAPTERS:
        for p in paras:
            assert " ".join(p.split()) in " ".join(full.split())


def test_header_like_text_in_body_is_kept(tmp_path):
    """Header text appearing once in the body (not in the margin) must stay."""
    path = corpus.make_book_pdf(tmp_path / "b.pdf")
    pdf = pymupdf.open(path)
    pdf[1].insert_text((72, 400), corpus.HEADER + " dibahas di sini.", fontsize=11, fontname="helv")
    out = tmp_path / "b2.pdf"
    pdf.save(out)
    doc = process_pdf(out, ocr=None)
    assert corpus.HEADER + " dibahas di sini." in " ".join(s.text for s in doc.sections)


def test_line_wrap_hyphenation_and_reduplication(tmp_path):
    doc = process_pdf(corpus.make_wrapped_pdf(tmp_path / "w.pdf"), ocr=None)
    text = doc.sections[0].text
    assert "menggunakan" in text
    assert "anak-anak" in text
    assert "dengan nyaman di perangkat Android." in text  # merged across page break
    assert doc.report["merged_across_pages"] == 1
    assert doc.sections[0].end_page == 2


def test_join_lines_unit():
    assert join_lines(["kata-", "kata lain"]) == "kata-kata lain"
    assert join_lines(["peme-", "rintah"]) == "pemerintah"
    assert join_lines(["COVID-", "19 menyebar"]) == "COVID- 19 menyebar"  # not lowercase: keep


def test_two_column_reading_order(tmp_path):
    doc = process_pdf(corpus.make_two_column_pdf(tmp_path / "c.pdf"), ocr=None)
    text = doc.sections[0].text
    assert text.index("Kolom kiri paragraf kedua") < text.index("Kolom kanan")


@requires_tesseract
def test_scanned_page_uses_ocr(tmp_path):
    ocr = TesseractOCR("ind+eng")
    if not ocr.available():
        pytest.skip("tesseract language data missing")
    doc = process_pdf(corpus.make_scanned_pdf(tmp_path / "s.pdf"), ocr=ocr)
    assert doc.report["ocr_pages"] == [1]
    text = " ".join(s.text for s in doc.sections).lower()
    assert "pindaian" in text and "ocr" in text


def test_scanned_page_without_ocr_is_flagged_not_skipped(tmp_path):
    doc = process_pdf(corpus.make_scanned_pdf(tmp_path / "s.pdf"), ocr=None)
    assert doc.report["review_pages"][0]["page"] == 1
    assert "OCR tidak tersedia" in doc.report["review_pages"][0]["reason"]
    assert doc.sections and doc.sections[0].needs_review
    assert "perlu ditinjau" in doc.sections[0].title


def test_unavailable_ocr_object_is_treated_as_missing(tmp_path):
    ocr = TesseractOCR("xxx")  # language that is never installed
    assert not ocr.available()
    doc = process_pdf(corpus.make_scanned_pdf(tmp_path / "s.pdf"), ocr=ocr)
    assert doc.report["review_pages"]


def test_empty_pdf_flags_blank_page(tmp_path):
    doc = process_pdf(corpus.make_empty_pdf(tmp_path / "e.pdf"), ocr=None)
    assert doc.report["review_pages"][0]["reason"].startswith("Halaman kosong")
    assert "warning" in doc.report


def test_malformed_pdf_raises_user_error(tmp_path):
    with pytest.raises(PdfError):
        process_pdf(corpus.make_malformed_pdf(tmp_path / "m.pdf"), ocr=None)


def test_encrypted_pdf_raises_user_error(tmp_path):
    path = corpus.make_book_pdf(tmp_path / "b.pdf")
    pdf = pymupdf.open(path)
    out = tmp_path / "enc.pdf"
    pdf.save(out, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="rahasia", owner_pw="rahasia")
    with pytest.raises(PdfError, match="kata sandi"):
        process_pdf(out, ocr=None)


def test_page_limit(tmp_path):
    with pytest.raises(PdfError, match="batas"):
        process_pdf(corpus.make_book_pdf(tmp_path / "b.pdf"), ocr=None, max_pages=2)


@pytest.mark.parametrize("text,expected", [
    ("12", True), ("- 3 -", True), ("Halaman 4 dari 10", True), ("Page 7", True), ("iv", True),
    ("Bab 3", False), ("12 orang hadir", False),
])
def test_page_number_detection(text, expected):
    assert is_page_number(text) is expected


def test_long_sections_are_split_at_paragraphs():
    sec = Section("Bab Panjang", 1, ["a" * 400, "b" * 400, "c" * 400], 1, 2)
    parts = split_long([sec], max_chars=900)
    assert [p.title for p in parts] == ["Bab Panjang", "Bab Panjang (bagian 2)"]
    assert all(len(p.text) <= 900 for p in parts)
    assert "".join(p.text.replace("\n", "") for p in parts) == "a" * 400 + "b" * 400 + "c" * 400
