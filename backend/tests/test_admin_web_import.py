from fastapi.testclient import TestClient

from app.main import app
from app.modules.auth.dependencies import require_admin
from app.modules.documents import admin_router
from app.modules.documents.web_import import WebImportResult


def test_admin_can_import_public_web_page(monkeypatch) -> None:
    captured: dict = {}

    async def fake_import(request):
        captured["request"] = request
        return WebImportResult(
            document={
                "id": "cfcf6243-c221-43f8-8b6b-048e7f387f47",
                "title": request.title,
                "source_url": request.url,
            },
            was_duplicate=False,
            title=request.title,
            source_url=request.url,
        )

    monkeypatch.setattr(admin_router.web_import_service, "import_page", fake_import)
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
    request = captured["request"]
    assert request.url == "https://example.com/policy"
    assert request.title == "My policy page"
    assert request.imported_by == "e8c8a641-9532-40c9-96cc-32e929f0bb33"
    assert request.imported_via == "web_import_admin"


def test_web_import_requires_admin() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/admin/documents/import-url",
            json={"url": "https://example.com/policy"},
        )
    assert response.status_code == 401
