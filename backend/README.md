# Policy in Action Library Backend

This is the backend skeleton for the Policy in Action Library project.

The Demo1 PDF/RAG backend has been migrated into this modular structure. Auth,
document management, ingestion, local pgvector retrieval, LangGraph chat, and
LLM settings now live under `app/` routes and services. Crawler endpoints remain
as placeholders for a future feature branch.

## MVP Modules

- Admin document management: upload, metadata editing, processing status.
- Ingestion pipeline: file validation, PDF/text extraction, chunking, indexing.
- RAG pipeline: embeddings, retrieval, answer generation, citations.
- Crawler pipeline: trusted source registration, crawl jobs, future external data collection.
- Document library: list, filter, detail, chunks.

## Quick Start

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
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

## Local Database

The migrated backend uses local PostgreSQL with pgvector by default:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/policy_library
DATABASE_ENABLED=true
LLM_API_KEY=your_llm_api_key_here
LLM_CHAT_MODEL=deepseek-v4-flash
LLM_BASE_URL=https://api.deepseek.com
APP_SECRET=replace-for-local-development
```

The local schema is maintained in:

```text
supabase/local_schema.sql
```

If `DATABASE_ENABLED=false`, the app can still start for health checks and
contract tests; database-backed endpoints initialise the schema when used.

## Suggested Branches

- `feature/admin-upload`
- `feature/ingestion-pipeline`
- `feature/rag-chat`
- `feature/crawler-sources`
- `feature/document-library`
- `feature/database-schema`

Keep `master` stable. Implement features in branches and merge back regularly after tests pass.
