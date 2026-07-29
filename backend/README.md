# Policy in Action Library Backend

FastAPI backend for the Policy in Action Library. It provides authentication,
PDF ingestion and retrieval-augmented chat, trusted-source crawling, document
catalogue APIs, and PostgreSQL/pgvector persistence.

## Technology stack

- Python 3.11+
- FastAPI and Uvicorn
- PostgreSQL with pgvector
- SQLAlchemy/asyncpg and psycopg
- LangGraph and OpenAI-compatible chat APIs
- HTTPX, Playwright, and optional Firecrawl crawling

## Project layout

```text
backend/
|-- app/
|   |-- api/             # Top-level FastAPI router composition
|   |-- core/            # Shared configuration, database, and ORM foundations
|   `-- modules/
|       |-- auth/        # Authentication and authorization
|       |-- settings/    # Runtime LLM settings
|       |-- documents/   # Library, PDF ingestion, chunks, and embeddings
|       |-- crawling/    # Sources, jobs, crawlers, cleaning, and crawl results
|       |-- chat/        # RAG answer generation and LangGraph workflow
|       `-- system/      # Health and application metadata endpoints
|-- database/init.sql    # PostgreSQL/pgvector schema dump
|-- docs/                # API contracts and Git workflow
|-- examples/sources/    # Example crawler source configurations
`-- tests/
```

Each business module owns its HTTP routes, schemas, services, persistence code,
and models. Cross-module calls should use the owning module's service or query
interface; modules must not duplicate persistence code for data owned elsewhere.

The document module separates persistence by responsibility under
`modules/documents/repositories/`: document records and governance, extracted
content and metadata, catalogue response queries, embeddings, and processing
jobs. Routes use the catalogue repository while ingestion services use the
record/content repositories directly.

## Local setup

From the repository root, run:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev,database,crawlers]"
Copy-Item .env.example .env
```

Playwright is only needed for sites that require browser rendering. Install its
browser separately when required:

```powershell
playwright install chromium
```

OCR (scanned/image-only PDF pages) requires the Tesseract system binary, not just
the `pytesseract` pip package. Install it separately if you're running outside
Docker (the Docker image installs it automatically):

```powershell
winget install --id UB-Mannheim.TesseractOCR -e   # Windows
```

```bash
apt-get install tesseract-ocr   # Debian/Ubuntu
brew install tesseract          # macOS
```

Without it, PDF processing still works normally -- pages that would need OCR
are just left with empty text (logged as a warning) instead of being recognized.

Uploads also accept Word (`.docx`), plain text (`.txt`), and Markdown (`.md`)
files alongside PDFs -- see `app/modules/documents/extraction.py` for the
per-extension extractor dispatch. These formats need no extra system
dependencies beyond the pip packages.

Start the API from `backend/`:

```powershell
uvicorn app.main:app --reload
```

The API is then available at:

- Swagger UI: <http://127.0.0.1:8000/docs>
- OpenAPI JSON: <http://127.0.0.1:8000/openapi.json>
- Health check: <http://127.0.0.1:8000/api/v1/health>

## Configuration

Settings are loaded from `backend/.env`. Start with `.env.example`; the main
options are:

| Variable | Purpose | Local default |
| --- | --- | --- |
| `APP_ENV` | Runtime environment name | `development` |
| `APP_DEBUG` | FastAPI debug mode | `true` |
| `API_V1_PREFIX` | Prefix for application routes | `/api/v1` |
| `APP_SECRET` | Signs access tokens; replace outside local development | development value |
| `DATABASE_ENABLED` | Enables the async database lifecycle and crawler persistence | `false` |
| `DATABASE_URL` | PostgreSQL connection URL | local `ai_policy` database |
| `PERSISTENCE_BACKEND` | Crawler repository backend (`database` or in-memory fallback) | `database` |
| `CRAWLING_ENABLED` | Allows non-dry-run crawls to contact remote sites | `false` |
| `FIRECRAWL_API_KEY` | Optional Firecrawl fallback credential | empty |
| `EMBEDDING_MODEL_NAME` | Local embedding model for vector search | `BAAI/bge-small-en-v1.5` |
| `DEFAULT_EMBEDDING_DIMENSIONS` | Output dimensions of the embedding model | `384` |
| `MODEL_CACHE_DIR` | Path to cache downloaded HuggingFace models | `data/model_cache` |
| `ADMIN_REGISTER_SECRET` | Secret required to register admin accounts | empty |

See `app/core/config.py` for the complete list and validation rules. Never commit
the populated `.env` file.

Provider base URLs and models come from the model catalog. Provider API keys
and the default chat selection are managed in **Manage > LLM & API keys** and
stored in the deployment's cached runtime settings file, not environment
variables.

## PostgreSQL and pgvector

Authentication, uploaded PDF workflows, embeddings, and document APIs require a
PostgreSQL database. The crawler source/job repositories can use temporary
in-memory storage while `DATABASE_ENABLED=false`; that data is lost when the
process stops.

1. Create a PostgreSQL database and ensure the server has the `vector` extension.
2. Apply `database/init.sql` to a fresh development database.
3. Apply all migration files in order.
4. Set the connection values in `.env`.

```dotenv
DATABASE_ENABLED=true
DATABASE_URL=postgresql+asyncpg://appuser:yourpassword@localhost:5432/testdb
DATABASE_POOL_PRE_PING=true
PERSISTENCE_BACKEND=database
```

For example, with the PostgreSQL CLI installed:

```powershell
# Fresh install — apply base schema first, then all migrations in order
psql -U appuser -d testdb -f database/init.sql
psql -U appuser -d testdb -f database/migrations/001_add_answer_mode.sql
psql -U appuser -d testdb -f database/migrations/002_add_model_to_chat_messages.sql
```

**Important:** `database/init.sql` contains destructive `DROP … IF EXISTS` statements.
Use it only for a fresh or local database, never to update an existing production instance.
For existing databases, run only the numbered migration files in `database/migrations/`.

When adding a new column or table:
1. Add it to `init.sql` (keeps fresh installs in sync)
2. Write a new `NNN_description.sql` in `database/migrations/` (for existing installs)
3. Run the migration against the live database before deploying code that depends on it

### Moving model providers and endpoints to production

The built-in provider and endpoint presets live in code and are idempotently
upserted when the catalog is first read. Endpoints added in **Manage > LLM &
API keys**, however, are written directly to the local `model_providers` and
`model_catalog` tables.

Do not export the whole database or hand-write INSERT statements. Export only
the non-secret catalog:

```powershell
docker compose exec backend python scripts/model_catalog_transfer.py export --output /app/data/model-catalog.json
```

The bind mount makes that file available at
`backend/data/model-catalog.json`. Copy it to the production checkout, apply
the new idempotent provider migration to an existing database, and import:

```powershell
Get-Content backend/database/migrations/009_add_model_providers.sql -Raw |
  docker compose exec -T db psql -U appuser -d testdb
docker compose exec backend python scripts/model_catalog_transfer.py import --input /app/data/model-catalog.json
```

The import performs upserts and does not delete online-only rows. The JSON
contains provider metadata and endpoint facts only; API keys remain in each
deployment's runtime settings and must be entered separately in the production
admin UI.

With `DATABASE_ENABLED=false`, the application can still start and expose its
health endpoint, and crawler source/job APIs use their in-memory fallback. Routes
whose repositories connect directly to PostgreSQL still require a working
`DATABASE_URL`.

## Authentication

Register or log in through `/api/v1/auth`, then send the returned token as:

```http
Authorization: Bearer <token>
```

`/api/v1/chat` and `/api/v1/auth/me` require an authenticated user. Settings and
all `/api/v1/admin/documents` routes require the `admin` role.

## Main API groups

All application routes use the `/api/v1` prefix.

| Group | Routes |
| --- | --- |
| Health | `GET /health` |
| Authentication | `POST /auth/register`, `POST /auth/login`, `GET /auth/me` |
| Settings | `GET /settings`, `PUT /settings` (admin) |
| Documents | list, search, detail, chunks, versions, and assets under `/documents` |
| Crawled documents | list, search, detail, versions, and assets under `/crawled-documents` |
| Crawl sources | CRUD under `/crawl-sources` |
| Crawl jobs | list, detail, and create under `/crawl-jobs` |
| PDF administration | upload, rescan, update, delete, and processing status under `/admin/documents` |
| RAG chat (streaming) | `POST /chat/ask-stream` — SSE streaming Q&A |
| Chat models | `GET /chat/models` — available LLM providers and models |
| Chat history | `GET /chat/sessions`, `GET /chat/sessions/{id}/messages` |

The generated Swagger UI is the source of truth for request/response schemas.
See [docs/API_CONTRACTS.md](docs/API_CONTRACTS.md) for the maintained endpoint
index, access requirements, and example payloads.

## RAG Pipeline

The chat endpoint uses a LangGraph workflow with a 3-level evidence gate:

```
Question ──► embed query ──► pgvector ANN search ──► cross-encoder rerank
                                                            │
              ┌─────────────────────────────────────────────┘
              ▼
        Evidence Gate (3 levels)
        1. Cosine distance ≤ 0.45         (vector similarity threshold)
        2. Reranker score ≥ -7.0          (cross-encoder relevance score)
        3. LLM semantic judge             (GPT/Claude confirms relevance)
              │
        pass ─┤─ fail ──► "insufficient evidence" refusal
              │
              ▼
        Generate answer (streamed as SSE tokens)
```

The SSE event sequence for each question is:
`retrieving → thinking → token × N → citations → done`

Per-message model selection is supported: pass `"model": "openai/gpt-4o"` (or any
`"provider/model-id"` from `GET /chat/models`) in the request body to override the
default model for that message. The resolved model name is echoed back in the
`citations` SSE event.

## Crawler safety

Remote crawling is disabled by default. Keep `CRAWLING_ENABLED=false` while
developing API contracts or use the default `dry_run=true` when creating a crawl
job. A real crawl requires both:

```dotenv
CRAWLING_ENABLED=true
```

and a job submitted with `dry_run=false`.

On Windows, run Uvicorn without `--reload` when a source needs Playwright:

```powershell
python -m uvicorn app.main:app
```

The reload subprocess can use an event loop that cannot launch Playwright's
browser process. For ordinary sites, prefer `crawler_preference` set to `http`
or `auto`.

## Quality checks

Run these commands from `backend/`:

```powershell
pytest
ruff check app tests
```

Tests default to safe configuration and do not enable real network crawling.

## Container deployment

The repository root contains `compose.yaml` and `.env.production.example` for the
backend and Caddy-served frontend. The Compose stack expects PostgreSQL to be
provided separately through `DATABASE_URL` and persists backend files by mounting
`backend/data` into the container.
