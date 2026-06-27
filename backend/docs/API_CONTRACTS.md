# API Contracts

Implemented endpoints:

- `GET /api/v1/health`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `GET /api/v1/settings`
- `PUT /api/v1/settings`
- `GET /api/v1/documents` — list locally managed PDF documents (auth-optional)
- `GET /api/v1/documents/{document_id}` — document detail
- `GET /api/v1/documents/{document_id}/file` — download PDF (auth required)
- `GET /api/v1/documents/{document_id}/pages` — extracted page text (auth required)
- `GET /api/v1/documents/{document_id}/chunks` — RAG chunks (auth-optional)
- `GET /api/v1/crawled-documents` — list documents ingested by the crawler pipeline
- `GET /api/v1/crawled-documents/search?q={query}` — full-text search by filename, title, summary, or keywords
- `GET /api/v1/crawled-documents/{document_id}` — crawled document detail with metadata, source info, and snippet previews
- `GET /api/v1/crawled-documents/{document_id}/chunks` — snippet previews
- `GET /api/v1/crawled-documents/{document_id}/versions` — version history
- `GET /api/v1/crawled-documents/{document_id}/assets` — linked assets
- `POST /api/v1/admin/documents`
- `POST /api/v1/admin/documents/rescan`
- `PATCH /api/v1/admin/documents/{document_id}`
- `DELETE /api/v1/admin/documents/{document_id}`
- `GET /api/v1/admin/documents/{document_id}/processing-status`
- `POST /api/v1/chat`
- `GET /api/v1/sources`
- `POST /api/v1/sources`
- `GET /api/v1/sources/{source_id}`
- `PATCH /api/v1/sources/{source_id}`
- `DELETE /api/v1/sources/{source_id}`
- `GET /api/v1/crawl-jobs`
- `POST /api/v1/crawl-jobs`
- `GET /api/v1/crawl-jobs/{job_id}`

Local PostgreSQL/pgvector schema lives in `supabase/local_schema.sql`.
