# Policy in Action Library Backend

FastAPI backend for the Policy in Action Library. It provides authentication,
PDF ingestion, evidence-aware web search, permanent URL import,
retrieval-augmented chat, document catalogue APIs, and PostgreSQL/pgvector persistence.

## Technology stack

- Python 3.11+
- FastAPI and Uvicorn
- PostgreSQL with pgvector
- SQLAlchemy/asyncpg and psycopg
- LangGraph and OpenAI-compatible chat APIs
- HTTPX and optional Firecrawl-backed web search

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
|       |-- web_search/  # Search providers, page fetching, and URL safety
|       |-- chat/        # RAG answer generation and LangGraph workflow
|       `-- system/      # Health and application metadata endpoints
|-- database/init.sql    # PostgreSQL/pgvector schema dump
|-- docs/                # API contracts and Git workflow
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
pip install -e ".[dev,database,web-search]"
Copy-Item .env.example .env
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

When upgrading an existing pre-durable-task database, first stop the API and
document workers and run this from `backend/` with the service's environment:

```powershell
python -m app.modules.documents.migrate
```

This applies only migration 028 in a single transaction to the database selected
by `backend/.env` and environment overrides. It preserves existing users and
documents and recovers incomplete uploads. It does not apply earlier migrations
or initialize a fresh database. API and standalone worker startup now check for
the two required task tables and stop with this command if they are missing.
Do not run `database/init.sql` against an existing database: it resets tables.

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
| `APP_SECRET` | Optional explicit access-token signing secret | generated file |
| `APP_SECRET_FILE` | Persisted access-token signing secret | `data/app_secret` |
| `DATABASE_ENABLED` | Enables database access and lifecycle | `false` |
| `DATABASE_URL` | PostgreSQL connection URL | local `ai_policy` database |
| `DATABASE_POOL_MIN_SIZE` / `DATABASE_POOL_MAX_SIZE` | Repository pool connections per process | `1` / `5` |
| `DATABASE_POOL_TIMEOUT` / `DATABASE_POOL_MAX_WAITING` | Borrow wait seconds / maximum queued borrowers | `2` / `20` |
| `UPLOAD_MAX_BYTES` / `UPLOAD_CHUNK_BYTES` | Maximum file size / bounded save buffer | `20971520` / `1048576` |
| `UPLOAD_REQUEST_OVERHEAD_BYTES` | Extra request body budget for multipart metadata | `262144` |
| `RUNTIME_SETTINGS_PATH` | Cached provider settings file, relative to backend or absolute | `data/settings.json` |
| `FIRECRAWL_API_KEY` | Optional Firecrawl web-search credential | empty |
| `EMBEDDING_MODEL_NAME` | Local embedding model for vector search | `BAAI/bge-small-en-v1.5` |
| `DEFAULT_EMBEDDING_DIMENSIONS` | Output dimensions of the embedding model | `384` |
| `MODEL_CACHE_DIR` | Path to cache downloaded HuggingFace models | `data/model_cache` |

See `app/core/config.py` for the complete list and validation rules. Never commit
the populated `.env` file.

Provider base URLs and models come from the model catalog. Provider API keys
and the default chat selection are managed in **Manage > LLM & API keys** and
stored in the deployment's cached runtime settings file, not environment
variables.

## PostgreSQL and pgvector

Authentication, uploaded-file workflows, embeddings, and document APIs require a
PostgreSQL database.

1. Create a PostgreSQL database and ensure the server has the `vector` extension.
2. Apply `database/init.sql` to a fresh development database.
3. Apply all migration files in order.
4. Set the connection values in `.env`.

```dotenv
DATABASE_ENABLED=true
DATABASE_URL=postgresql+asyncpg://appuser:yourpassword@localhost:5432/testdb
DATABASE_POOL_PRE_PING=true
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
health endpoint. Repository-backed routes return database-unavailable responses;
enable the database and supply a working `DATABASE_URL` to use them.

Repositories share a psycopg pool with bounded acquisition waits. Pool capacity
errors return `503` with `Retry-After: 1`. Inspect per-process limits and counters
through the admin-only `GET /api/v1/admin/database-pool`. LangGraph's checkpointer
uses a separate long-lived async connection with an internal lock; the Repository
limit is not the total server connection limit.

Uploads default to 20 MiB per file. The frontend reads
`GET /api/v1/documents/upload-limits` before sending files. The backend independently
limits the request body and actual file size, saves with bounded buffers in a
worker thread, and cleans failed or duplicate staged files. This is one multipart
request per file; browser chunk uploads and resumable uploads are not implemented.
To allow 100 MiB, set `UPLOAD_MAX_BYTES=104857600` and restart the backend.

See [the Chinese implementation and learning guide](docs/CONNECTION_POOL_AND_UPLOAD_GUIDE.md)
for database communication, pool sizing, asyncio, the complete upload journey,
verification evidence, and interview demonstrations.

### Durable document processing

Apply `database/migrations/028_durable_document_tasks.sql` once to an existing
database while the old backend is stopped, then start this version. Fresh Compose
volumes include it automatically; restarting an existing volume does not apply
new migrations. Existing incomplete document rows are backfilled with tasks.

Completed file uploads commit document metadata, a `document_tasks` row, and an
optional upload request key together. Fixed workers claim tasks using PostgreSQL
`FOR UPDATE SKIP LOCKED`, heartbeat their leases, and retry failed/expired attempts
within a budget. Publication checks the current lease and atomically writes the
index together with success. This uses PostgreSQL as the durable broker.

By default each backend process runs three document workers. For a separate
worker process, start the API with `DOCUMENT_TASK_WORKERS=0`, and in another
terminal using the same database and accessible document storage run:

```powershell
python -m app.modules.documents.worker --concurrency 3 --warmup
```

`--warmup` loads the configured embedding model before tasks are claimed. Each
process has its own connection pool. The task lease coordinates ownership across
processes; worker concurrency is still a per-process setting.

The admin workspace shows task states, attempt counts, errors, and a retry button.
`GET /api/v1/admin/document-tasks` lists tasks;
`POST /api/v1/admin/document-tasks/{id}/retry` retries a failed task. Uploads accept
`Idempotency-Key` scoped to the administrator: identical retries reuse document
and task IDs; changed input with the same key returns `409`. Selected frontend
File objects keep their keys across retries, without persistence across a page reload.

To run real PDF, HTTP, process-crash, local-embedding, and multi-account tests
against an initialized disposable local database ending in `_tests`:

```powershell
python scripts/verify_durable_tasks.py --database-url postgresql://user:password@127.0.0.1:5432/durable_demo_tests
```

The verifier starts and stops only its own API/worker subprocesses. It creates
synthetic policy PDFs, kills a worker after real extraction, checks recovery,
performs concurrent uploads and reads, restores temporarily unavailable storage,
and saves its report under `tmp/durable-demo/`. Remote chat models are not invoked.
See [the Chinese task, idempotency and concurrency guide](docs/DURABLE_DOCUMENT_TASKS_GUIDE.md)
for the implementation boundaries, test results, interview demos, and a code-linked
review of the first-stage connection pool work.

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

## Quality checks

Run these commands from `backend/`:

```powershell
pytest
ruff check .
ruff format --check .
```

Tests use mocked providers and do not perform real web searches. Real PostgreSQL
tests are opt-in: set `TEST_DATABASE_URL` to an initialized disposable database
with pgvector and the numbered migrations, then run `pytest` again. They never
fall back to the application's `.env` database. Frontend checks are `npm test`
and `npm run build` from `frontend/`.

## Container deployment

The repository root contains a self-contained `compose.yaml` for PostgreSQL/pgvector,
the backend, and the Caddy-served frontend. No environment file is required. Optional
deployment overrides are documented in the root `.env.example`; backend files and the
generated token-signing secret persist under `backend/data`.

See the repository root README for the first-administrator invitation workflow.
