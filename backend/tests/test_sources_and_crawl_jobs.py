from fastapi.testclient import TestClient

from app.main import app


def test_create_source_and_dry_run_crawl_job() -> None:
    with TestClient(app) as client:
        source_response = client.post(
            "/api/v1/sources",
            json={
                "name": "OECD.AI Policy Initiatives",
                "start_url": "https://oecd.ai/en/dashboards/policy-initiatives",
                "allowed_domains": ["oecd.ai"],
                "include_patterns": [
                    "^/en/dashboards/policy-initiatives(?:/.*)?$",
                ],
                "crawler_preference": "auto",
                "max_pages": 3000,
                "max_depth": 3,
            },
        )
        assert source_response.status_code == 201

        crawl_job_response = client.post(
            "/api/v1/crawl-jobs",
            json={"source_id": source_response.json()["id"], "dry_run": True},
        )

    assert crawl_job_response.status_code == 202
    assert crawl_job_response.json()["source_id"] == source_response.json()["id"]
