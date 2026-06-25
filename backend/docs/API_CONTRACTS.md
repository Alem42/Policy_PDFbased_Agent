# API Contracts

Current skeleton endpoints:

- `GET /api/v1/health`
- `GET /api/v1/documents`
- `GET /api/v1/documents/{document_id}` returns a document detail payload with
  metadata, summary, source information, snippet previews, and total snippet count.
- `GET /api/v1/documents/{document_id}/chunks` returns available snippet previews.
- `POST /api/v1/admin/documents`
- `PATCH /api/v1/admin/documents/{document_id}`
- `DELETE /api/v1/admin/documents/{document_id}`
- `GET /api/v1/admin/documents/{document_id}/processing-status`
- `POST /api/v1/chat`
- `POST /api/v1/trusted-sources`
- `GET /api/v1/trusted-sources`
- `POST /api/v1/crawl-jobs`
- `GET /api/v1/crawl-jobs/{job_id}`

Most endpoints return `501 Not Implemented` until their feature branch provides the real implementation.
