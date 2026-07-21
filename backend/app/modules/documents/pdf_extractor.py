from __future__ import annotations

import logging
import re
import shutil
from collections.abc import Callable
from io import BytesIO
from pathlib import Path

import fitz  # PyMuPDF, used only to render scanned pages down to images for OCR
import pytesseract
from PIL import Image
from pypdf import PdfReader

from app.core.config import get_settings

logger = logging.getLogger(__name__)

OCR_RENDER_DPI = 200

# Common Windows install locations for the Tesseract-OCR system binary.
# pytesseract shells out to "tesseract" by default, relying on PATH -- but on
# Windows, freshly-installed PATH entries don't propagate to processes whose
# parent shell/IDE was already running, so a working install can still fail
# to be found. Linux (Docker, apt-installed tesseract-ocr) always resolves
# via PATH and never needs this lookup.
_WINDOWS_TESSERACT_CANDIDATES = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]

_tesseract_resolved = False


def _resolve_tesseract_cmd() -> None:
    global _tesseract_resolved
    if _tesseract_resolved:
        return
    _tesseract_resolved = True

    override = get_settings().ocr_tesseract_cmd
    if override:
        pytesseract.pytesseract.tesseract_cmd = override
        return

    if shutil.which(pytesseract.pytesseract.tesseract_cmd):
        return

    for candidate in _WINDOWS_TESSERACT_CANDIDATES:
        if Path(candidate).is_file():
            pytesseract.pytesseract.tesseract_cmd = candidate
            logger.info("Found Tesseract at %s (not on PATH)", candidate)
            return


class PdfExtractor:
    """Extracts PDF pages and removes common retrieval noise."""

    def extract(self, path: Path, on_ocr_start: Callable[[], None] | None = None) -> list[dict]:
        reader = PdfReader(BytesIO(path.read_bytes()))
        pages = [
            {
                "file": path.name,
                "page": page_number,
                "text": (page.extract_text() or "").strip(),
            }
            for page_number, page in enumerate(reader.pages, start=1)
        ]
        pages = self._ocr_low_text_pages(path, pages, on_ocr_start)
        return self.clean(pages)

    def _ocr_low_text_pages(
        self,
        path: Path,
        pages: list[dict],
        on_ocr_start: Callable[[], None] | None = None,
    ) -> list[dict]:
        """Re-read scanned/image-only pages via OCR.

        Runs per page rather than once for the whole document, since mixed
        documents -- e.g. a digitally authored report with a scanned
        signature page appended -- are common in practice. A page whose
        native pypdf extraction came back near-empty is assumed to be an
        image, rendered to a bitmap, and passed through Tesseract.
        """
        min_chars = get_settings().ocr_min_text_chars
        needs_ocr = [page for page in pages if len(page["text"]) < min_chars]
        if not needs_ocr:
            return pages

        if on_ocr_start:
            on_ocr_start()

        _resolve_tesseract_cmd()

        try:
            document = fitz.open(path)
        except Exception as exc:
            logger.warning("Could not open %s for OCR rendering: %s", path.name, exc)
            return pages

        try:
            for page in needs_ocr:
                ocr_text = self._ocr_page(document, page["page"])
                if ocr_text:
                    page["text"] = ocr_text
        finally:
            document.close()
        return pages

    @staticmethod
    def _ocr_page(document: fitz.Document, page_number: int) -> str:
        try:
            pixmap = document[page_number - 1].get_pixmap(dpi=OCR_RENDER_DPI)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            return pytesseract.image_to_string(image, lang=get_settings().ocr_languages).strip()
        except pytesseract.TesseractNotFoundError:
            logger.warning(
                "Page %d looks scanned but the Tesseract OCR engine is not installed; "
                "leaving it as empty text.",
                page_number,
            )
            return ""
        except Exception as exc:
            logger.warning("OCR failed for page %d: %s", page_number, exc)
            return ""

    def clean(self, pages: list[dict]) -> list[dict]:
        repeated_lines = self._repeated_margin_lines(pages)
        cleaned_pages: list[dict] = []
        in_references = False

        for index, page in enumerate(pages):
            text = page["text"]
            if in_references or self._looks_like_table_of_contents(text):
                cleaned_pages.append({**page, "text": ""})
                continue

            lines = [
                line
                for line in text.splitlines()
                if self._normalise_noise_line(line) not in repeated_lines
            ]
            text = "\n".join(lines).strip()
            if index > len(pages) * 0.7:
                match = re.search(
                    r"(?im)^\s*(references|bibliography|works cited)\s*$",
                    text,
                )
                if match:
                    text = text[: match.start()].strip()
                    in_references = True
            cleaned_pages.append({**page, "text": text})

        return cleaned_pages

    @staticmethod
    def _normalise_noise_line(line: str) -> str:
        clean = re.sub(r"\s+", " ", line).strip().lower()
        return re.sub(r"\d+", "#", clean)

    def _repeated_margin_lines(self, pages: list[dict]) -> set[str]:
        counts: dict[str, int] = {}
        for page in pages:
            lines = [line.strip() for line in page["text"].splitlines() if line.strip()]
            for line in lines[:3] + lines[-3:]:
                normalised = self._normalise_noise_line(line)
                if 4 <= len(normalised) <= 120:
                    counts[normalised] = counts.get(normalised, 0) + 1
        threshold = max(3, len(pages) // 4)
        return {line for line, count in counts.items() if count >= threshold}

    @staticmethod
    def _looks_like_table_of_contents(text: str) -> bool:
        lower = text.lower()
        dot_leaders = len(re.findall(r"\.{3,}\s*\d+", text))
        numbered_entries = len(re.findall(r"^\s*\d+(\.\d+)*\s+.+\s+\d+\s*$", text, re.MULTILINE))
        return ("table of contents" in lower or "contents" in lower) and (
            dot_leaders >= 4 or numbered_entries >= 6
        )


pdf_extractor = PdfExtractor()
