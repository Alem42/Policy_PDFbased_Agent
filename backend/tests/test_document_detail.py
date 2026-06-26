from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.document import DocumentRead, DocumentVersionRead
from app.repositories.document_repository import document_repository


def test_document_detail_includes_metadata_source_and_snippets() -> None:
    source_id = uuid4()
    document = DocumentRead(
        source_id=source_id,
        canonical_url="https://example.org/policy.pdf",
        title="AI Policy Strategy",
        summary="A short policy summary.",
        country="Exampleland",
        content_hash="a" * 64,
        metadata={"policy_area": "AI governance"},
    )
    version = DocumentVersionRead(
        document_id=document.id,
        version=1,
        content_hash=document.content_hash,
        title=document.title,
        clean_markdown="First useful excerpt.\n\nSecond useful excerpt.",
    )
    document_repository.save_local(document, version, persist=False)

    with TestClient(app) as client:
        response = client.get(f"/api/v1/documents/{document.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["document_id"] == str(document.id)
    assert payload["summary"] == "A short policy summary."
    assert payload["metadata"]["title"] == "AI Policy Strategy"
    assert payload["metadata"]["country_region"] == "Exampleland"
    assert payload["source"]["source_url"] == "https://example.org/policy.pdf"
    assert payload["snippet_count"] == 2
    assert payload["snippets"][0]["text_preview"] == "First useful excerpt."


def test_document_chunks_returns_available_snippets() -> None:
    source_id = uuid4()
    document = DocumentRead(
        source_id=source_id,
        canonical_url="https://example.org/another-policy.pdf",
        title="Another AI Policy",
        content_hash="b" * 64,
    )
    version = DocumentVersionRead(
        document_id=document.id,
        version=1,
        content_hash=document.content_hash,
        clean_markdown="Excerpt one.\n\nExcerpt two.\n\nExcerpt three.",
    )
    document_repository.save_local(document, version, persist=False)

    with TestClient(app) as client:
        response = client.get(f"/api/v1/documents/{document.id}/chunks?limit=2")

    assert response.status_code == 200
    assert [item["text_preview"] for item in response.json()] == [
        "Excerpt one.",
        "Excerpt two.",
    ]


def test_search_documents_matches_filename() -> None:
    source_id = uuid4()
    document = DocumentRead(
        source_id=source_id,
        canonical_url="https://example.org/files/unique-filename-strategy.pdf",
        title="Filename Search Policy",
        content_hash="c" * 64,
    )
    document_repository.save_local(document, persist=False)

    with TestClient(app) as client:
        response = client.get("/api/v1/documents/search?q=unique-filename")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["document_id"] == str(document.id)
    assert payload[0]["original_filename"] == "unique-filename-strategy.pdf"
    assert "filename" in payload[0]["match_fields"]


def test_search_documents_matches_keywords() -> None:
    source_id = uuid4()
    document = DocumentRead(
        source_id=source_id,
        canonical_url="https://example.org/files/keyword-policy.pdf",
        title="Keyword Search Policy",
        content_hash="d" * 64,
        metadata={"keywords": ["frontier governance marker"]},
    )
    document_repository.save_local(document, persist=False)

    with TestClient(app) as client:
        response = client.get("/api/v1/documents/search?q=frontier%20governance")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["document_id"] == str(document.id)
    assert payload[0]["keywords"] == ["frontier governance marker"]
    assert "keywords" in payload[0]["match_fields"]
