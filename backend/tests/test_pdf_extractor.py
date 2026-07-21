from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import fitz
import pytesseract
import pytest

from app.modules.documents.pdf_extractor import PdfExtractor


@pytest.fixture
def tmp_path():
    """Local replacement for pytest's tmp_path fixture: the shared Windows
    pytest-of-<user> temp root is permission-denied in this environment, so
    use our own throwaway directory instead."""
    path = Path(tempfile.gettempdir()) / f"pdf_extractor_test_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _build_pdf(tmp_path: Path, *, native_text: str | None) -> Path:
    """A one-page PDF. With native_text, the page has real selectable text;
    without it, the page is blank (no text, no image) -- close enough to a
    scanned page for extract() to treat it as needing OCR."""
    doc = fitz.open()
    page = doc.new_page(width=400, height=200)
    if native_text is not None:
        page.insert_text((20, 100), native_text, fontsize=18)
    path = tmp_path / "test.pdf"
    doc.save(path)
    doc.close()
    return path


def test_page_with_enough_native_text_is_not_sent_to_ocr(tmp_path, monkeypatch):
    pdf_path = _build_pdf(
        tmp_path, native_text="This page has plenty of real selectable text on it."
    )
    ocr_calls = []
    monkeypatch.setattr(
        "app.modules.documents.pdf_extractor.pytesseract.image_to_string",
        lambda *a, **k: ocr_calls.append(1) or "SHOULD NOT BE USED",
    )

    pages = PdfExtractor().extract(pdf_path)

    assert not ocr_calls
    assert "real selectable text" in pages[0]["text"]


def test_low_text_page_is_recovered_via_ocr(tmp_path, monkeypatch):
    pdf_path = _build_pdf(tmp_path, native_text=None)
    monkeypatch.setattr(
        "app.modules.documents.pdf_extractor.pytesseract.image_to_string",
        lambda *a, **k: "Recovered via OCR",
    )

    pages = PdfExtractor().extract(pdf_path)

    assert pages[0]["text"] == "Recovered via OCR"


def test_missing_tesseract_binary_degrades_gracefully(tmp_path, monkeypatch):
    pdf_path = _build_pdf(tmp_path, native_text=None)

    def _raise(*args, **kwargs):
        raise pytesseract.TesseractNotFoundError()

    monkeypatch.setattr("app.modules.documents.pdf_extractor.pytesseract.image_to_string", _raise)

    pages = PdfExtractor().extract(pdf_path)

    assert pages[0]["text"] == ""


def test_mixed_document_only_ocrs_the_page_that_needs_it(tmp_path, monkeypatch):
    doc = fitz.open()
    doc.new_page(width=400, height=200).insert_text(
        (20, 100), "Native text on page one.", fontsize=18
    )
    doc.new_page(width=400, height=200)  # blank -- simulates a scanned page
    path = tmp_path / "mixed.pdf"
    doc.save(path)
    doc.close()

    ocr_pages = []

    def _fake_ocr(image, lang=None):
        ocr_pages.append(lang)
        return "Recovered via OCR"

    monkeypatch.setattr(
        "app.modules.documents.pdf_extractor.pytesseract.image_to_string", _fake_ocr
    )

    pages = PdfExtractor().extract(path)

    assert len(ocr_pages) == 1
    assert "Native text on page one" in pages[0]["text"]
    assert pages[1]["text"] == "Recovered via OCR"


def test_on_ocr_start_fires_only_when_a_page_actually_needs_ocr(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.modules.documents.pdf_extractor.pytesseract.image_to_string",
        lambda *a, **k: "Recovered via OCR",
    )
    ocr_started = []

    scanned_path = _build_pdf(tmp_path, native_text=None)
    PdfExtractor().extract(scanned_path, on_ocr_start=lambda: ocr_started.append(1))
    assert ocr_started == [1]

    ocr_started.clear()
    native_path = _build_pdf(tmp_path, native_text="Plenty of real selectable text here.")
    PdfExtractor().extract(native_path, on_ocr_start=lambda: ocr_started.append(1))
    assert ocr_started == []
