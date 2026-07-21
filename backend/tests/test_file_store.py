from __future__ import annotations

import pytest

from app.modules.documents.file_store import DocumentFileStore


@pytest.mark.parametrize(
    "filename",
    ["report.pdf", "report.docx", "notes.txt", "readme.md"],
)
def test_safe_filename_accepts_supported_extensions(filename):
    assert DocumentFileStore.safe_filename(filename) == filename


@pytest.mark.parametrize("filename", ["report.doc", "image.png", "archive.zip", "noext"])
def test_safe_filename_rejects_unsupported_extensions(filename):
    with pytest.raises(ValueError):
        DocumentFileStore.safe_filename(filename)


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("report.pdf", "application/pdf"),
        (
            "report.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        ("notes.txt", "text/plain"),
        ("readme.md", "text/markdown"),
    ],
)
def test_mime_type_for_known_extensions(filename, expected):
    assert DocumentFileStore.mime_type_for(filename) == expected


def test_is_valid_content_checks_pdf_magic_bytes():
    assert DocumentFileStore.is_valid_content("report.pdf", b"%PDF-1.4 ...")
    assert not DocumentFileStore.is_valid_content("report.pdf", b"not a pdf")


def test_is_valid_content_checks_docx_zip_signature():
    assert DocumentFileStore.is_valid_content("report.docx", b"PK\x03\x04rest of zip")
    assert not DocumentFileStore.is_valid_content("report.docx", b"%PDF-1.4 pretending to be docx")


def test_is_valid_content_accepts_decodable_text():
    assert DocumentFileStore.is_valid_content("notes.txt", b"plain text")
    assert DocumentFileStore.is_valid_content("readme.md", b"# heading")


def test_is_valid_content_rejects_binary_garbage_for_text_files():
    assert not DocumentFileStore.is_valid_content("notes.txt", b"\x00\x01\x02binary")
