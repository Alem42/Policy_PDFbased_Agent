-- Migration 020: lifecycle and review policy for permanently imported pages.

CREATE TABLE IF NOT EXISTS "public"."web_document_governance" (
  "document_id" uuid PRIMARY KEY REFERENCES "public"."documents"("id") ON DELETE CASCADE,
  "lifecycle_status" text NOT NULL DEFAULT 'active',
  "refresh_interval_days" integer NOT NULL DEFAULT 30,
  "first_imported_at" timestamptz NOT NULL DEFAULT now(),
  "last_fetched_at" timestamptz NOT NULL DEFAULT now(),
  "last_checked_at" timestamptz,
  "next_review_at" timestamptz NOT NULL DEFAULT (now() + interval '30 days'),
  "last_http_status" integer,
  "last_refresh_error" text,
  "content_version" integer NOT NULL DEFAULT 1,
  "created_by" uuid REFERENCES "public"."app_users"("id") ON DELETE SET NULL,
  "created_at" timestamptz NOT NULL DEFAULT now(),
  "updated_at" timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT "web_document_governance_status_check"
    CHECK (lifecycle_status IN ('active', 'stale', 'archived')),
  CONSTRAINT "web_document_governance_interval_check"
    CHECK (refresh_interval_days BETWEEN 1 AND 3650),
  CONSTRAINT "web_document_governance_version_check"
    CHECK (content_version >= 1)
);

CREATE INDEX IF NOT EXISTS "idx_web_document_governance_review"
  ON "public"."web_document_governance" ("lifecycle_status", "next_review_at");

-- Backfill existing permanent web imports.
INSERT INTO "public"."web_document_governance" (
  document_id, first_imported_at, last_fetched_at, next_review_at, created_by
)
SELECT id, uploaded_at, uploaded_at, uploaded_at + interval '30 days', imported_by
FROM "public"."documents"
WHERE canonical_url IS NOT NULL
ON CONFLICT (document_id) DO NOTHING;
