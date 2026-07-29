"""L2 (normalised-content-hash) dedup helper and the repository lookups it
relies on. See documents/service.py process_document()/save_web_import()."""

from __future__ import annotations

from uuid import uuid4

from app.modules.documents.file_store import DocumentFileStore
from app.modules.documents.repositories.documents import document_repository


def test_normalized_content_hash_ignores_whitespace_and_case() -> None:
    a = DocumentFileStore.normalized_content_hash("Hello   World\n\n")
    b = DocumentFileStore.normalized_content_hash("hello world")
    assert a == b


def test_normalized_content_hash_differs_for_different_content() -> None:
    a = DocumentFileStore.normalized_content_hash("Hello World")
    b = DocumentFileStore.normalized_content_hash("Goodbye World")
    assert a != b


def test_find_by_content_hash_returns_none_for_unknown_hash() -> None:
    assert document_repository.find_by_content_hash(f"nonexistent-{uuid4()}") is None


def test_find_by_source_url_returns_none_for_unknown_url() -> None:
    assert document_repository.find_by_source_url(f"https://example.com/{uuid4()}") is None
