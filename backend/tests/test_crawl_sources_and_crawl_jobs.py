from fastapi.testclient import TestClient

from app.main import app


def test_create_crawl_source_and_dry_run_crawl_job() -> None:
    with TestClient(app) as client:
        crawl_source_response = client.post(
            "/api/v1/crawl-sources",
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
        assert crawl_source_response.status_code == 201

        crawl_job_response = client.post(
            "/api/v1/crawl-jobs",
            json={"crawl_source_id": crawl_source_response.json()["id"], "dry_run": True},
        )

    assert crawl_job_response.status_code == 202
    assert crawl_job_response.json()["crawl_source_id"] == crawl_source_response.json()["id"]
