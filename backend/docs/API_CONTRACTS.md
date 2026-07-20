# API Contracts

Current HTTP contract for the Policy in Action Library backend. The generated
OpenAPI document and Swagger UI remain the source of truth:

- Swagger UI: `GET /docs`
- ReDoc: `GET /redoc`
- OpenAPI JSON: `GET /openapi.json`

## Conventions

- API base path: `/api/v1`
- Request and response bodies use JSON unless stated otherwise.
- UUID path parameters use standard UUID strings.
- Protected routes expect `Authorization: Bearer <token>`.
- Validation errors use FastAPI's standard `422` response body.
- Missing resources return `404` with a JSON `detail` field.

Access levels used below:

- **Public**: no access token is required.
- **User**: any authenticated `user` or `admin` account.
- **Admin**: an authenticated account whose role is `admin`.

## Health

| Method | Path | Access | Description |
| --- | --- | --- | --- |
| `GET` | `/api/v1/health` | Public | Return service, environment, crawling, and database status. |

## Authentication

| Method | Path | Access | Success | Description |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/auth/register` | Public | `201` | Create an account and return its access token. |
| `POST` | `/api/v1/auth/login` | Public | `200` | Authenticate and return an access token. |
| `GET` | `/api/v1/auth/me` | User | `200` | Return the current user. |

Register and login accept:

```json
{
  "username": "researcher",
  "password": "replace-me",
  "role": "user"
}
```

`role` is optional and accepts `user` or `admin`. The response shape is:

```json
{
  "token": "<signed-token>",
  "user": {
    "id": "<uuid>",
    "uid": "<uuid>",
    "username": "researcher",
    "role": "user",
    "created_at": "<ISO-8601 timestamp>"
  }
}
```

Authentication uses PostgreSQL even when `DATABASE_ENABLED=false`, so these
routes still require a working `DATABASE_URL` and initialized schema.

## Runtime settings

| Method | Path | Access | Description |
| --- | --- | --- | --- |
| `GET` | `/api/v1/settings` | Admin | Return masked LLM configuration and its active sources. |
| `PUT` | `/api/v1/settings` | Admin | Update the API key and/or chat model. |

The update body accepts `llm_api_key` and `llm_chat_model`. The legacy aliases
`deepseek_api_key` and `deepseek_chat_model` are also accepted.

## Documents

These routes expose the unified PostgreSQL-backed document catalogue.

| Method | Path | Access | Description |
| --- | --- | --- | --- |
| `GET` | `/api/v1/documents?limit=100` | Public | List documents; `limit` is between 1 and 500. |
| `GET` | `/api/v1/documents/search?q={query}&page=1&page_size=20` | Public | Search and paginate documents from PostgreSQL. Supports `status`, `policy_area`, `country_region`, `source_type`, and `sort`; `page_size` is between 1 and 100. |
| `GET` | `/api/v1/documents/{document_id}` | Public | Return document detail and metadata. |
| `GET` | `/api/v1/documents/{document_id}/file` | Public | Download the original PDF. |
| `GET` | `/api/v1/documents/{document_id}/chunks?limit=20` | Public | Return chunk previews; `limit` is between 1 and 100. |
| `GET` | `/api/v1/documents/{document_id}/versions` | Public | Return version history. |
| `GET` | `/api/v1/documents/{document_id}/assets` | Public | Return linked assets. |

The former `/pages` endpoint is not part of the current router.

Document search returns `{items, page, page_size, total, pages}`. Supported
sort values are `uploaded_desc`, `name_asc`, `year_desc`, and `chunks_desc`.
An omitted or blank `q` returns a paginated catalogue without a text-search
condition.

## Crawled documents

| Method | Path | Access | Description |
| --- | --- | --- | --- |
| `GET` | `/api/v1/crawled-documents` | Public | List crawled documents; optionally filter by `crawl_source_id`. |
| `GET` | `/api/v1/crawled-documents/search?q={query}&limit=20` | Public | Search crawled content; `limit` is between 1 and 100. |
| `GET` | `/api/v1/crawled-documents/{crawled_document_id}?snippet_limit=8` | Public | Return detail with up to 0–50 snippet previews. |
| `GET` | `/api/v1/crawled-documents/{crawled_document_id}/versions` | Public | Return version history. |
| `GET` | `/api/v1/crawled-documents/{crawled_document_id}/assets` | Public | Return linked assets. |

There is no separate crawled-document `/chunks` endpoint in the current API;
snippet previews are included in the detail response.

## Crawl sources

| Method | Path | Access | Success | Description |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/crawl-sources` | Public | `200` | List configured sources. |
| `POST` | `/api/v1/crawl-sources` | Public | `201` | Create a source. |
| `GET` | `/api/v1/crawl-sources/{crawl_source_id}` | Public | `200` | Return one source. |
| `PATCH` | `/api/v1/crawl-sources/{crawl_source_id}` | Public | `200` | Partially update a source. |
| `DELETE` | `/api/v1/crawl-sources/{crawl_source_id}` | Public | `204` | Delete a source. |

A source create body has this shape:

```json
{
  "name": "OECD AI policy initiatives",
  "start_url": "https://example.org/policies",
  "allowed_domains": ["example.org"],
  "include_patterns": [],
  "exclude_patterns": [],
  "crawler_preference": "auto",
  "max_pages": 100,
  "max_documents": 100,
  "max_depth": 3,
  "enabled": true,
  "schedule": null,
  "config": {}
}
```

`crawler_preference` accepts `auto`, `http`, `playwright`, or `firecrawl`.
The old `/api/v1/sources` path has been replaced by `/api/v1/crawl-sources`.

## Crawl jobs

| Method | Path | Access | Success | Description |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/crawl-jobs` | Public | `200` | List crawl jobs. |
| `POST` | `/api/v1/crawl-jobs` | Public | `202` | Create a job and schedule it as a background task. |
| `GET` | `/api/v1/crawl-jobs/{crawl_job_id}` | Public | `200` | Return job status and counters. |

Create a safe dry-run job with:

```json
{
  "crawl_source_id": "<uuid>",
  "dry_run": true
}
```

`dry_run` defaults to `true`. A non-dry-run job can contact remote sites only
when `CRAWLING_ENABLED=true`. Creating a job for a disabled source returns
`409`; an unknown source returns `404`.

When `DATABASE_ENABLED=false`, crawl source, crawl job, and crawled-document
repositories use process-local in-memory storage. That data is not durable.

## Document administration

All routes in this group require the `admin` role and PostgreSQL.

| Method | Path | Success | Description |
| --- | --- | --- | --- |
| `POST` | `/api/v1/admin/documents` | `202` | Upload a PDF and queue background processing. |
| `POST` | `/api/v1/admin/documents/rescan` | `200` | Rescan and reprocess the document library. |
| `PATCH` | `/api/v1/admin/documents/{document_id}` | `200` | Partially update document metadata. |
| `DELETE` | `/api/v1/admin/documents/{document_id}` | `204` | Delete a document. |
| `GET` | `/api/v1/admin/documents/{document_id}/processing-status` | `200` | Return processing state and progress. |

Upload uses `multipart/form-data`. The `file` field is required; optional fields
are `title`, `source_organisation`, `policy_area`, `source_url`,
`country_or_region`, `published_year`, `tags`, and `credibility_level`.
Credibility accepts `official`, `academic`, `institutional`, or `unknown`.

Metadata updates use JSON and accept `title`, `summary`, `source_organisation`,
`source_url`, `policy_area`, `country_or_region`, `published_year`, `tags`,
`credibility_level`, `approved`, and `access_level`.

## RAG chat

| Method | Path | Access | Description |
| --- | --- | --- | --- |
| `POST` | `/api/v1/chat` | User | Ask a question over selected documents and receive citations. |

Example request:

```json
{
  "question": "What policy instruments are recommended?",
  "document_ids": ["<uuid>"],
  "filenames": [],
  "filters": {
    "policy_area": null,
    "country_or_region": null,
    "source_organisation": null,
    "tags": [],
    "published_year_from": null,
    "published_year_to": null
  },
  "top_k": 6,
  "model": null,
  "response_mode": "researcher",
  "answer_mode": "analysis"
}
```

`response_mode` accepts `researcher` or `student` (writing style).
`answer_mode` accepts `analysis` (selected documents only) or `chat`
(open discussion that may use general knowledge). Defaults are
`researcher` and `analysis`.

At least one `document_id` or `filename` is required. `top_k` must be between 1
and 20. Model-provider failures return `502`; missing documents return `404`.
The response contains `answer`, `citations`, `truncated`, `evidence_sufficient`,
`response_mode`, and `answer_mode`.

## Persistence contract

The current PostgreSQL/pgvector schema is [database/init.sql](../database/init.sql).
It is a schema dump for initializing a fresh database and contains destructive
`DROP` statements; it is not a production migration.
