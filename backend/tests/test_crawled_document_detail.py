from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.repositories.crawled_document_repository import (
    CrawledDocumentRepository,
    crawled_document_repository,
)
from app.schemas.crawled_document import (
    CrawledDocumentRead,
    CrawledDocumentVersionRead,
)


async def test_crawled_document_detail_includes_metadata_source_and_snippets(
    tmp_path,
) -> None:
    repository = CrawledDocumentRepository(tmp_path / "crawled_documents.json")
    source_id = uuid4()
    document = CrawledDocumentRead(
        source_id=source_id,
        canonical_url="https://example.org/policy.pdf",
        title="AI Policy Strategy",
        summary="A short policy summary.",
        country="Exampleland",
        content_hash="a" * 64,
        metadata={"policy_area": "AI governance"},
    )
    version = CrawledDocumentVersionRead(
        crawled_document_id=document.id,
        version=1,
        content_hash=document.content_hash,
        title=document.title,
        clean_markdown="First useful excerpt.\n\nSecond useful excerpt.",
    )
    repository.save_local(document, version, persist=False)

    detail = await repository.get_detail(document.id)

    assert detail is not None
    assert detail.crawled_document_id == document.id
    assert detail.summary == "A short policy summary."
    assert detail.metadata.title == "AI Policy Strategy"
    assert detail.metadata.country == "Exampleland"
    assert detail.source.source_url == "https://example.org/policy.pdf"
    assert detail.snippet_count == 2
    assert detail.snippets[0].text_preview == "First useful excerpt."


async def test_crawled_document_detail_respects_snippet_limit(tmp_path) -> None:
    repository = CrawledDocumentRepository(tmp_path / "crawled_documents.json")
    source_id = uuid4()
    document = CrawledDocumentRead(
        source_id=source_id,
        canonical_url="https://example.org/another-policy.pdf",
        title="Another AI Policy",
        content_hash="b" * 64,
    )
    version = CrawledDocumentVersionRead(
        crawled_document_id=document.id,
        version=1,
        content_hash=document.content_hash,
        clean_markdown="Excerpt one.\n\nExcerpt two.\n\nExcerpt three.",
    )
    repository.save_local(document, version, persist=False)

    detail = await repository.get_detail(document.id, snippet_limit=2)

    assert detail is not None
    assert [item.text_preview for item in detail.snippets] == [
        "Excerpt one.",
        "Excerpt two.",
    ]


async def test_search_crawled_documents_matches_canonical_url(tmp_path) -> None:
    repository = CrawledDocumentRepository(tmp_path / "crawled_documents.json")
    source_id = uuid4()
    document = CrawledDocumentRead(
        source_id=source_id,
        canonical_url="https://example.org/files/unique-filename-strategy.pdf",
        title="Filename Search Policy",
        content_hash="c" * 64,
    )
    repository.save_local(document, persist=False)

    results = await repository.search_crawled_documents("unique-filename")

    assert results[0].crawled_document_id == document.id
    assert results[0].canonical_url == "https://example.org/files/unique-filename-strategy.pdf"
    assert "canonical_url" in results[0].match_fields


async def test_search_crawled_documents_matches_metadata_keywords(tmp_path) -> None:
    repository = CrawledDocumentRepository(tmp_path / "crawled_documents.json")
    source_id = uuid4()
    document = CrawledDocumentRead(
        source_id=source_id,
        canonical_url="https://example.org/files/keyword-policy.pdf",
        title="Keyword Search Policy",
        content_hash="d" * 64,
        metadata={"keywords": ["frontier governance marker"]},
    )
    repository.save_local(document, persist=False)

    results = await repository.search_crawled_documents("frontier governance")

    assert results[0].crawled_document_id == document.id
    assert results[0].keywords == ["frontier governance marker"]
    assert "metadata" in results[0].match_fields


def test_crawled_document_detail_api_returns_saved_document() -> None:
    source_id = uuid4()
    document = CrawledDocumentRead(
        source_id=source_id,
        canonical_url="https://example.org/api-policy.pdf",
        title="API Policy",
        content_hash="e" * 64,
    )
    version = CrawledDocumentVersionRead(
        crawled_document_id=document.id,
        version=1,
        content_hash=document.content_hash,
        clean_markdown="API excerpt.",
    )
    crawled_document_repository.save_local(document, version, persist=False)

    with TestClient(app) as client:
        response = client.get(f"/api/v1/crawled-documents/{document.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["crawled_document_id"] == str(document.id)
    assert payload["source"]["source_url"] == "https://example.org/api-policy.pdf"
