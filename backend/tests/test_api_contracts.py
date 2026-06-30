from fastapi.testclient import TestClient

from app.main import app


def test_chat_requires_authentication() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat",
            json={"question": "What works?", "document_ids": [], "top_k": 3},
        )

    assert response.status_code == 401


def test_root_points_to_versioned_health() -> None:
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.json()["health"] == "/api/v1/health"


def test_versioned_auth_route_is_mounted() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/auth/login", json={})

    assert response.status_code == 422
