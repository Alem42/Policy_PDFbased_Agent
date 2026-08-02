from __future__ import annotations

import pytest

from app.modules.documents import service
from app.modules.documents.exceptions import DuplicateDocumentError


@pytest.mark.asyncio
async def test_save_web_import_maps_byte_duplicate_to_success(monkeypatch) -> None:
    monkeypatch.setattr(service.document_repository, "find_by_source_url", lambda _: None)

    async def duplicate_upload(*args, **kwargs):
        raise DuplicateDocumentError("existing-1", "existing.md")

    monkeypatch.setattr(service, "save_upload", duplicate_upload)
    monkeypatch.setattr(
        service.document_content_repository,
        "get_detail_record",
        lambda identifier, **kwargs: {"id": identifier, "title": "Existing"},
    )

    document, was_duplicate = await service.save_web_import(
        url="https://example.com/copy",
        title="Copy",
        markdown="same bytes",
        imported_by="user-1",
    )
    assert was_duplicate is True
    assert document["id"] == "existing-1"


@pytest.mark.asyncio
async def test_save_web_import_persists_title_after_processing(monkeypatch) -> None:
    monkeypatch.setattr(service.document_repository, "find_by_source_url", lambda _: None)

    async def save_upload(*args, **kwargs):
        return {"id": "new-1"}

    monkeypatch.setattr(service, "save_upload", save_upload)
    monkeypatch.setattr(service, "process_document", lambda _: None)
    monkeypatch.setattr(service.document_repository, "find_by_content_hash", lambda *a, **k: None)
    monkeypatch.setattr(service, "_find_near_duplicate", lambda *args: None)
    captured: dict = {}

    def update_metadata(identifier: str, payload: dict):
        captured.update({"identifier": identifier, "payload": payload})
        return {"id": identifier, "title": payload["title"]}

    monkeypatch.setattr(service.document_content_repository, "update_metadata", update_metadata)

    document, was_duplicate = await service.save_web_import(
        url="https://example.com/policy",
        title="Human supplied title",
        markdown="unique content",
        imported_by="user-1",
    )
    assert was_duplicate is False
    assert document["title"] == "Human supplied title"
    assert captured == {
        "identifier": "new-1",
        "payload": {"title": "Human supplied title"},
    }


@pytest.mark.asyncio
async def test_save_web_import_cleans_up_failed_processing(monkeypatch) -> None:
    monkeypatch.setattr(service.document_repository, "find_by_source_url", lambda _: None)

    async def save_upload(*args, **kwargs):
        return {"id": "new-1"}

    monkeypatch.setattr(service, "save_upload", save_upload)

    def fail_processing(_: str) -> None:
        raise RuntimeError("embedding failed")

    monkeypatch.setattr(service, "process_document", fail_processing)
    deleted: list[str] = []
    monkeypatch.setattr(service, "delete_document", deleted.append)

    with pytest.raises(RuntimeError, match="embedding failed"):
        await service.save_web_import(
            url="https://example.com/policy",
            title="Policy",
            markdown="content",
            imported_by="user-1",
        )
    assert deleted == ["new-1"]
