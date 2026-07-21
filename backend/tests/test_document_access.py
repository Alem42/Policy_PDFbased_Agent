from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.modules.auth.dependencies import get_optional_user
from app.modules.documents import router as document_router


def test_admin_document_list_includes_restricted(monkeypatch) -> None:
    captured: dict[str, bool] = {}

    async def fake_list_documents(*, limit: int, include_restricted: bool):
        captured["include_restricted"] = include_restricted
        return []

    monkeypatch.setattr(
        document_router.document_catalogue_repository,
        "list_documents",
        fake_list_documents,
    )
    app.dependency_overrides[get_optional_user] = lambda: {"role": "admin"}
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/documents")
    finally:
        app.dependency_overrides.pop(get_optional_user, None)

    assert response.status_code == 200
    assert captured["include_restricted"] is True


def test_document_file_route_returns_pdf(monkeypatch, tmp_path) -> None:
    document_id = uuid4()
    pdf_path = tmp_path / "policy.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 test")

    monkeypatch.setattr(
        document_router,
        "get_document_record",
        lambda identifier, include_restricted: {
            "id": identifier,
            "original_filename": "policy.pdf",
        },
    )
    monkeypatch.setattr(
        document_router,
        "resolve_document_file",
        lambda identifier, include_restricted: pdf_path,
    )

    with TestClient(app) as client:
        response = client.get(f"/api/v1/documents/{document_id}/file")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == b"%PDF-1.4 test"
