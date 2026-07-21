from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.modules.documents.docx_extractor import docx_extractor
from app.modules.documents.pdf_extractor import pdf_extractor
from app.modules.documents.text_extractor import text_extractor

# Extension -> extractor. Keep in sync with file_store.SUPPORTED_MIME_TYPES.
_EXTRACTORS = {
    ".pdf": pdf_extractor,
    ".docx": docx_extractor,
    ".txt": text_extractor,
    ".md": text_extractor,
}


def extract_document(path: Path, on_ocr_start: Callable[[], None] | None = None) -> list[dict]:
    """Extract pages from a document, dispatching by file extension.

    on_ocr_start is only meaningful for PDFs -- it's invoked once, right
    before Tesseract runs, so callers can surface an "OCR in progress"
    status while pypdf/docx/text extraction never triggers it.
    """
    extractor = _EXTRACTORS.get(path.suffix.lower())
    if extractor is None:
        raise ValueError(f"Unsupported file type: {path.suffix}")
    if extractor is pdf_extractor:
        return extractor.extract(path, on_ocr_start=on_ocr_start)
    return extractor.extract(path)
