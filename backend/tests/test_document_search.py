from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.modules.documents import router as document_router
from app.modules.documents.repositories.catalogue import DocumentCatalogueRepository
from app.modules.documents.repositories.documents import DocumentRepository


def _document_row(**overrides) -> dict:
    row = {
        "id": uuid4(),
        "name": "policy.pdf",
        "original_filename": "policy.pdf",
        "title": "Climate Policy",
        "summary": "A national transition plan",
        "source_type": "report",
        "source_organisation": "Policy Department",
        "country_region": "Australia",
        "language": "English",
        "year": 2026,
        "publication_date": "2026-06-30",
        "policy_areas": ["Environment"],
        "keywords": ["climate", "transition"],
        "mime_type": "application/pdf",
        "file_size": 1234,
        "page_count": 8,
        "chunk_count": 24,
        "status": "ready",
        "approved": True,
        "access_level": "public",
        "uploaded_at": "2026-06-30T00:00:00Z",
        "processed_at": "2026-06-30T00:01:00Z",
    }
    row.update(overrides)
    return row


def test_search_result_keeps_library_list_fields() -> None:
    result = DocumentCatalogueRepository._search_result(_document_row(), query="environment")

    assert result.source_type == "report"
    assert result.policy_areas == ["Environment"]
    assert result.page_count == 8
    assert result.chunk_count == 24
    assert result.file_size == 1234
    assert "policy_areas" in result.match_fields


def test_database_filters_ignore_blank_query_and_apply_exact_filters() -> None:
    clauses, values = DocumentRepository._filters(
        include_restricted=False,
        policy_area="Environment",
        country_or_region="Australia",
        source_organisation=None,
        tag=None,
        query="   ",
        status="ready",
        source_type="report",
    )

    assert "d.approved = true AND d.access_level = 'public'" in clauses
    assert "%s = ANY(m.policy_areas)" in clauses
    assert "d.status = %s" in clauses
    assert "m.source_type = %s" in clauses
    assert not any("ILIKE" in clause for clause in clauses)
    assert values == ["Environment", "Australia", "ready", "report"]


def test_database_text_search_covers_library_fields() -> None:
    clauses, values = DocumentRepository._filters(
        include_restricted=True,
        policy_area=None,
        country_or_region=None,
        source_organisation=None,
        tag=None,
        query=" climate ",
        status=None,
        source_type=None,
    )

    search_clause = clauses[0]
    assert "m.country_region ILIKE" in search_clause
    assert "m.source_type ILIKE" in search_clause
    assert "array_to_string(m.policy_areas" in search_clause
    assert "CAST(m.year AS TEXT) ILIKE" in search_clause
    assert values == ["%climate%"] * 9


def test_database_text_search_escapes_like_wildcards() -> None:
    clauses, values = DocumentRepository._filters(
        include_restricted=True,
        policy_area=None,
        country_or_region=None,
        source_organisation=None,
        tag=None,
        query="100%_complete!",
        status=None,
        source_type=None,
    )

    assert "ESCAPE '!'" in clauses[0]
    assert values == ["%100!%!_complete!!%"] * 9


def test_search_api_passes_pagination_filters_and_sort(monkeypatch) -> None:
    captured = {}

    async def fake_search(query, **kwargs):
        captured["query"] = query
        captured.update(kwargs)
        return {
            "items": [],
            "page": kwargs["page"],
            "page_size": kwargs["page_size"],
            "total": 42,
            "pages": 3,
        }

    monkeypatch.setattr(
        document_router.document_catalogue_repository,
        "search_documents",
        fake_search,
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/documents/search",
            params={
                "q": "climate",
                "status": "ready",
                "policy_area": "Environment",
                "country_region": "Australia",
                "source_type": "report",
                "sort": "year_desc",
                "page": 2,
                "page_size": 20,
            },
        )

    assert response.status_code == 200
    assert response.json()["total"] == 42
    assert captured == {
        "query": "climate",
        "status": "ready",
        "policy_area": "Environment",
        "country_region": "Australia",
        "source_type": "report",
        "sort": "year_desc",
        "page": 2,
        "page_size": 20,
        "include_restricted": False,
    }


def test_search_api_rejects_unknown_sort() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/documents/search?sort=drop_table")

    assert response.status_code == 422
