# Policy in Action Library Backend

FastAPI backend for policy data ingestion. The current branch implements the data-source and crawling foundation used to collect, clean, version, and persist policy documents before later RAG work.

## Current Scope

- Configurable trusted policy sources.
- Crawl job creation and status tracking.
- HTTP-first crawling with Playwright and Firecrawl fallback hooks.
- Configurable pagination and structured field extraction.
- HTML cleaning into markdown-like content.
- Incremental document sync with versions, assets, and missing-document tracking.
- OECD.AI policy initiatives adapter and config-only example.
- Supabase/PostgreSQL schema and migrations.

RAG chat, admin upload, and frontend UI are still separate future modules.

## Quick Start

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev,database,crawlers]"
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000/docs
```

## Run Tests

```powershell
cd backend
pytest
ruff check app tests
```

## Main Endpoints

- `GET /api/v1/health`
- `GET /api/v1/sources`
- `POST /api/v1/sources`
- `GET /api/v1/crawl-jobs`
- `POST /api/v1/crawl-jobs`
- `GET /api/v1/documents`
- `GET /api/v1/documents/{document_id}`
- `GET /api/v1/documents/{document_id}/versions`
- `GET /api/v1/documents/{document_id}/assets`

## Safety Defaults

Real network crawling is disabled by default:

```dotenv
CRAWLING_ENABLED=false
DATABASE_ENABLED=false
```

To run real crawls, explicitly enable crawling and submit a job with `dry_run=false`.

On Windows, use this command when a source explicitly needs Playwright:

```powershell
python -m uvicorn app.main:app
```

`--reload` can run Playwright under an event loop that cannot launch browser subprocesses.
For normal OECD/configured HTTP crawling, prefer `crawler_preference="http"` or `auto` without
`allow_playwright_fallback`.
