from fastapi.testclient import TestClient

from app.main import app
from app.modules.auth.dependencies import require_admin
from app.modules.documents import admin_router
from app.modules.documents.processing_queue import QueueState


def test_admin_upload_persists_source_provenance(monkeypatch) -> None:
    captured: dict = {}

    async def fake_save_upload(file, **kwargs):
        captured.update(kwargs)
        return {"id": "11111111-1111-1111-1111-111111111111", "status": "uploaded"}

    monkeypatch.setattr(admin_router, "save_upload", fake_save_upload)
    monkeypatch.setattr(
        admin_router,
        "update_document_metadata_record",
        lambda document_id, metadata: {
            "id": document_id,
            "status": "uploaded",
        },
    )
    monkeypatch.setattr(admin_router, "_run_process_document", lambda document_id: None)
    app.dependency_overrides[require_admin] = lambda: {
        "id": "admin-1",
        "role": "admin",
    }
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/admin/documents",
                files={"file": ("policy.pdf", b"%PDF-1.4 test", "application/pdf")},
                data={
                    "title": "Policy",
                    "source_url": " https://example.gov/policy.pdf ",
                },
            )
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 202
    assert captured == {
        "source_url": "https://example.gov/policy.pdf",
        "canonical_url": "https://example.gov/policy.pdf",
        "imported_by": "admin-1",
        "imported_via": "file_upload_admin",
    }


def test_processing_status_reports_real_queue_position(monkeypatch) -> None:
    document_id = "11111111-1111-1111-1111-111111111111"
    monkeypatch.setattr(
        admin_router,
        "get_document_detail",
        lambda requested_id, include_restricted: {
            "id": requested_id,
            "status": "uploaded",
            "error_message": None,
        },
    )
    monkeypatch.setattr(
        admin_router.document_processing_queue,
        "state",
        lambda requested_id: QueueState(status="queued", position=2),
    )
    app.dependency_overrides[require_admin] = lambda: {
        "id": "admin-1",
        "role": "admin",
    }
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/admin/documents/{document_id}/processing-status")
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 200
    assert response.json()["status"] == "queued"
    assert response.json()["progress_percent"] == 0
    assert response.json()["message"] == "Waiting for a processing slot (queue position 2)"
