from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from app.modules.documents.text_extractor import TextExtractor


@pytest.fixture
def tmp_path():
    path = Path(tempfile.gettempdir()) / f"text_extractor_test_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_extracts_txt_content_as_single_page(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("Line one.\nLine two.\n", encoding="utf-8")

    pages = TextExtractor().extract(path)

    assert len(pages) == 1
    assert pages[0]["page"] == 1
    assert "Line one." in pages[0]["text"]
    assert "Line two." in pages[0]["text"]


def test_extracts_markdown_content_verbatim(tmp_path):
    path = tmp_path / "readme.md"
    path.write_text("# Heading\n\nSome *markdown* body text.", encoding="utf-8")

    pages = TextExtractor().extract(path)

    assert "# Heading" in pages[0]["text"]
    assert "*markdown*" in pages[0]["text"]


def test_replaces_undecodable_bytes_instead_of_raising(tmp_path):
    path = tmp_path / "broken.txt"
    path.write_bytes(b"Valid text \xff\xfe invalid bytes")

    pages = TextExtractor().extract(path)

    assert "Valid text" in pages[0]["text"]
