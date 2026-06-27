# Policy in Action Library Backend

FastAPI backend for the Policy in Action Library project. The Demo1 PDF/RAG backend has been migrated into this modular structure. Auth, document management, ingestion, local pgvector retrieval, LangGraph chat, and LLM settings live under `app/` routes and services. The crawler foundation for data ingestion (configurable sources, crawl jobs, incremental sync) is integrated alongside the core features.

## Features

- Auth, document management, PDF extraction, and RAG chat (Demo1 core)
- Configurable trusted policy sources
- Crawl job creation and status tracking
- HTTP-first crawling with Playwright and Firecrawl fallback hooks
- Incremental document sync with versions, assets, and missing-document tracking
- OECD.AI policy initiatives adapter and config-only example
- PostgreSQL initialization schema

## Quick Start

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev,database,crawlers]"
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Open: http://127.0.0.1:8000/docs

## Run Tests

```powershell
cd backend
pytest
ruff check app tests
```

## Local Database

The backend uses local PostgreSQL with pgvector:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/policy_library
DATABASE_ENABLED=true
LLM_API_KEY=your_llm_api_key_here
LLM_CHAT_MODEL=deepseek-v4-flash
LLM_BASE_URL=https://api.deepseek.com
APP_SECRET=replace-for-local-development
```

The local schema is maintained in `supabase/local_schema.sql`.

If `DATABASE_ENABLED=false`, the app starts for health checks and contract tests; crawler repositories fall back to in-memory storage.

## Main Endpoints

- `GET /api/v1/health`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `GET /api/v1/settings` / `PUT /api/v1/settings`
- `GET /api/v1/documents` — local PDF document list
- `GET /api/v1/documents/{id}` / `/file` / `/pages` / `/chunks`
- `GET /api/v1/crawled-documents` — crawled document list (DB)
- `GET /api/v1/crawled-documents/search?q=`
- `GET /api/v1/crawled-documents/{id}` / `/chunks` / `/versions` / `/assets`
- `GET /api/v1/sources` / `POST /api/v1/sources`
- `GET /api/v1/crawl-jobs` / `POST /api/v1/crawl-jobs`
- `POST /api/v1/admin/documents`
- `POST /api/v1/chat`

## Safety Defaults

Real network crawling is disabled by default:

```dotenv
CRAWLING_ENABLED=false
DATABASE_ENABLED=false
```

To run real crawls, explicitly enable crawling and submit a job with `dry_run=false`.

On Windows, use this command when a source needs Playwright:

```powershell
python -m uvicorn app.main:app
```

`--reload` can run Playwright under an event loop that cannot launch browser subprocesses. For normal HTTP crawling, prefer `crawler_preference="http"` or `auto`.
