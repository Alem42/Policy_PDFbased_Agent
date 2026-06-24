from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def test_chat_placeholder() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/chat", json={"question": "What works?", "top_k": 3})

    assert response.status_code == 501


def test_document_chunks_placeholder() -> None:
    document_id = uuid4()
    with TestClient(app) as client:
        response = client.get(f"/api/v1/documents/{document_id}/chunks")

    assert response.status_code == 501
