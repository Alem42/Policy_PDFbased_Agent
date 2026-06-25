# API Contracts

Implemented endpoints:

- `GET /api/v1/health`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `GET /api/v1/settings`
- `PUT /api/v1/settings`
- `GET /api/v1/documents`
- `GET /api/v1/documents/{document_id}`
- `GET /api/v1/documents/{document_id}/file`
- `GET /api/v1/documents/{document_id}/pages`
- `GET /api/v1/documents/{document_id}/chunks`
- `POST /api/v1/admin/documents`
- `POST /api/v1/admin/documents/rescan`
- `PATCH /api/v1/admin/documents/{document_id}`
- `DELETE /api/v1/admin/documents/{document_id}`
- `GET /api/v1/admin/documents/{document_id}/processing-status`
- `POST /api/v1/chat`

Crawler skeleton endpoints:

- `POST /api/v1/trusted-sources`
- `GET /api/v1/trusted-sources`
- `POST /api/v1/crawl-jobs`
- `GET /api/v1/crawl-jobs/{job_id}`

The document, admin, auth, settings, and chat endpoints are migrated from Demo1
into the Demo1.1 module structure. Crawler endpoints still return
`501 Not Implemented` until the crawler module is built.

Local PostgreSQL/pgvector schema lives in `supabase/local_schema.sql`.
