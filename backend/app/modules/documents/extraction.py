from __future__ import annotations

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


def extract_document(path: Path) -> list[dict]:
    """Extract pages from a document, dispatching by file extension."""
    extractor = _EXTRACTORS.get(path.suffix.lower())
    if extractor is None:
        raise ValueError(f"Unsupported file type: {path.suffix}")
    return extractor.extract(path)
