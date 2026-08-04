# Web knowledge governance

Permanent web imports remain normal `documents` so retrieval, citations, and
access control stay shared with uploaded files. Web-only lifecycle data lives
in the one-to-one `web_document_governance` table.

## Lifecycle

- `active`: searchable and scheduled for review.
- `stale`: still searchable, but an administrator has marked it for review.
- `archived`: retained for audit/history and removed from ordinary-user search
  by setting `documents.approved=false`.

Each successful import (including a duplicate URL fetched again) updates
`last_fetched_at` and schedules `next_review_at` from
`refresh_interval_days`. It does not silently reactivate an archived page.

## Admin API

- `GET /api/v1/admin/documents/web-governance`
- `GET /api/v1/admin/documents/web-governance?due_only=true`
- `GET /api/v1/admin/documents/web-governance?lifecycle_status=stale`
- `PATCH /api/v1/admin/documents/{document_id}/web-governance`

Example update:

```json
{
  "lifecycle_status": "stale",
  "refresh_interval_days": 14,
  "next_review_at": "2026-08-20T00:00:00Z"
}
```

## Deliberately deferred

Migration 020 provides scheduling and lifecycle state, but does not run an
automatic refresh. A refresh worker still needs an explicit policy for HTTP
failures, changed content, version retention, re-index rollback, and admin
notifications before it is safe to automate overwrites.
