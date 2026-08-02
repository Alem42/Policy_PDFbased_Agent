from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.auth.dependencies import require_admin
from app.modules.documents import admin_router
from app.modules.documents.web_governance import WebGovernanceService


def governance_row(document_id: str) -> dict:
    now = datetime.now(UTC)
    return {
        "document_id": document_id,
        "lifecycle_status": "active",
        "refresh_interval_days": 30,
        "first_imported_at": now,
        "last_fetched_at": now,
        "last_checked_at": None,
        "next_review_at": now,
        "last_http_status": None,
        "last_refresh_error": None,
        "content_version": 1,
        "title": "Policy page",
        "canonical_url": "https://example.com/policy",
        "source_url": "https://example.com/policy",
        "document_status": "ready",
    }


class FakeRepository:
    def __init__(self) -> None:
        self.updated = None

    def register_import(self, document_id, *, created_by):
        return governance_row(document_id)

    def list_records(self, **_kwargs):
        return [governance_row("doc-1")]

    def update(self, document_id, **values):
        self.updated = (document_id, values)
        return governance_row(document_id)


def test_governance_service_validates_lifecycle_and_interval() -> None:
    service = WebGovernanceService(FakeRepository())

    with pytest.raises(ValueError, match="Unknown"):
        service.update("doc-1", lifecycle_status="deleted")
    with pytest.raises(ValueError, match="between 1 and 3650"):
        service.update("doc-1", refresh_interval_days=0)


def test_governance_service_delegates_valid_update() -> None:
    repository = FakeRepository()
    service = WebGovernanceService(repository)

    service.update("doc-1", lifecycle_status="stale", refresh_interval_days=14)

    assert repository.updated == (
        "doc-1",
        {
            "lifecycle_status": "stale",
            "refresh_interval_days": 14,
            "next_review_at": None,
        },
    )


def test_admin_can_list_web_governance(monkeypatch) -> None:
    document_id = str(uuid4())
    monkeypatch.setattr(
        admin_router.web_governance_service,
        "list",
        lambda **_kwargs: [governance_row(document_id)],
    )
    app.dependency_overrides[require_admin] = lambda: {
        "id": str(uuid4()),
        "role": "admin",
    }
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/admin/documents/web-governance?due_only=true")
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 200
    assert response.json()[0]["document_id"] == document_id
    assert response.json()[0]["lifecycle_status"] == "active"
