from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader


class PdfExtractor:
    """Extracts PDF pages and removes common retrieval noise."""

    def extract(self, path: Path) -> list[dict]:
        reader = PdfReader(BytesIO(path.read_bytes()))
        pages = [
            {
                "file": path.name,
                "page": page_number,
                "text": (page.extract_text() or "").strip(),
            }
            for page_number, page in enumerate(reader.pages, start=1)
        ]
        return self.clean(pages)

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
