from pathlib import Path
from uuid import uuid4

from app.crawlers.base import CrawledDocument
from app.repositories.crawled_document_repository import CrawledDocumentRepository
from app.schemas.crawled_document import CrawledDocumentStatus
from app.services.incremental_sync import IncrementalSyncService


async def test_incremental_add_unchanged_update_and_missing(tmp_path: Path) -> None:
    repository = CrawledDocumentRepository(tmp_path / "crawled_documents.json")
    service = IncrementalSyncService(repository)
    source_id = uuid4()

    first = await service.sync(
        source_id,
        [CrawledDocument(url="https://example.com/policy/1", markdown="version one")],
    )
    assert first.added == 1

    unchanged = await service.sync(
        source_id,
        [CrawledDocument(url="https://example.com/policy/1", markdown="version one")],
    )
    assert unchanged.unchanged == 1

    updated = await service.sync(
        source_id,
        [CrawledDocument(url="https://example.com/policy/1", markdown="version two")],
    )
    assert updated.updated == 1
    document = (await repository.list_crawled_documents(source_id))[0]
    assert document.current_version == 2
    assert len(await repository.versions(document.id)) == 2

    missing = await service.sync(source_id, [], mark_missing=True)
    assert missing.missing == 1
    assert (
        await repository.list_crawled_documents(source_id)
    )[0].status == CrawledDocumentStatus.MISSING


async def test_repository_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / "crawled_documents.json"
    source_id = uuid4()
    first_repository = CrawledDocumentRepository(path)
    await IncrementalSyncService(first_repository).sync(
        source_id,
        [CrawledDocument(url="https://example.com/policy/1", markdown="content")],
    )

    reloaded_repository = CrawledDocumentRepository(path)

    assert len(await reloaded_repository.list_crawled_documents(source_id)) == 1
