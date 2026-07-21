from __future__ import annotations

from pathlib import Path


class TextExtractor:
    """Extracts text from plain-text (.txt) and Markdown (.md) files.

    Like DocxExtractor, the whole file is treated as a single page -- these
    formats have no page concept, and the downstream chunker only needs a
    list of page dicts, not real pagination.
    """

    def extract(self, path: Path) -> list[dict]:
        text = path.read_bytes().decode("utf-8", errors="replace").strip()
        return [{"file": path.name, "page": 1, "text": text}]


text_extractor = TextExtractor()
