"""L2 (normalised-content-hash) dedup helper and the repository lookups it
relies on. See documents/service.py process_document()/save_web_import()."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.modules.documents.exceptions import DuplicateDocumentError
from app.modules.documents.file_store import DocumentFileStore
from app.modules.documents.repositories import documents as repository_module
from app.modules.documents.repositories.documents import DocumentRepository, document_repository


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


def test_canonical_url_unique_race_maps_to_existing_document(monkeypatch) -> None:
    class FakeUniqueViolation(Exception):
        diag = type("Diagnostic", (), {"constraint_name": "uq_documents_canonical_url"})()

    class FakeConnection:
        def execute(self, *_args, **_kwargs):
            raise FakeUniqueViolation("duplicate canonical URL")

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    repository = DocumentRepository()
    monkeypatch.setattr(repository_module, "UniqueViolation", FakeUniqueViolation)
    monkeypatch.setattr(repository_module, "get_connection", lambda: FakeConnection())
    monkeypatch.setattr(
        repository,
        "find_by_source_url",
        lambda _url: {"id": "existing-1", "original_filename": "existing.md"},
    )

    with pytest.raises(DuplicateDocumentError) as exc_info:
        repository.create(
            document_id=str(uuid4()),
            original_filename="new.md",
            stored_filename="new.md",
            file_path="new.md",
            content=b"new",
            checksum="checksum-new",
            mime_type="text/markdown",
            source_url="https://example.com/policy",
            canonical_url="https://example.com/policy",
            imported_by=None,
            imported_via="web_search",
        )

    assert exc_info.value.existing_id == "existing-1"
