from fastapi.testclient import TestClient

from app.main import app
from app.modules.auth.dependencies import require_admin
from app.modules.chat.rag.web_search.contracts import WebSearchResult
from app.modules.documents import admin_router


class FakeProvider:
    name = "fake"

    async def fetch_page(self, url: str) -> WebSearchResult:
        return WebSearchResult(
            url=url,
            title="Fetched policy page",
            content="# Policy\n\nReadable policy content.",
        )


def test_admin_can_import_public_web_page(monkeypatch) -> None:
    captured: dict = {}

    async def fake_validate(url: str) -> None:
        captured["validated_url"] = url

    async def fake_save_web_import(**kwargs):
        captured.update(kwargs)
        return (
            {
                "id": "cfcf6243-c221-43f8-8b6b-048e7f387f47",
                "title": kwargs["title"],
                "source_url": kwargs["url"],
            },
            False,
        )

    monkeypatch.setattr(admin_router, "validate_public_url", fake_validate)
    monkeypatch.setattr(admin_router, "get_active_web_search_provider", FakeProvider)
    monkeypatch.setattr(admin_router, "save_web_import", fake_save_web_import)
    app.dependency_overrides[require_admin] = lambda: {
        "id": "e8c8a641-9532-40c9-96cc-32e929f0bb33",
        "role": "admin",
    }
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/admin/documents/import-url",
                json={"url": "https://example.com/policy", "title": "My policy page"},
            )
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 201
    assert response.json() == {
        "id": "cfcf6243-c221-43f8-8b6b-048e7f387f47",
        "title": "My policy page",
        "source_url": "https://example.com/policy",
        "was_duplicate": False,
        "processing_status": "indexed",
    }
    assert captured["validated_url"] == "https://example.com/policy"
    assert captured["imported_by"] == "e8c8a641-9532-40c9-96cc-32e929f0bb33"
    assert captured["imported_via"] == "web_import_admin"


def test_web_import_requires_admin() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/admin/documents/import-url",
            json={"url": "https://example.com/policy"},
        )
    assert response.status_code == 401
