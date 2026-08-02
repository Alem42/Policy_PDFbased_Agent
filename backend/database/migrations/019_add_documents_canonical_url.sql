-- Migration 019: make normalised web-page identity concurrency-safe.

ALTER TABLE "public"."documents"
  ADD COLUMN IF NOT EXISTS "canonical_url" text;

-- WebImportService has normalised source_url since permanent imports were
-- introduced. Preserve one canonical owner for any historical duplicates;
-- the other documents remain available but no longer own the URL identity.
UPDATE "public"."documents"
SET "canonical_url" = "source_url"
WHERE "canonical_url" IS NULL AND "source_url" IS NOT NULL;

WITH ranked AS (
  SELECT id,
         row_number() OVER (
           PARTITION BY canonical_url
           ORDER BY uploaded_at ASC, id ASC
         ) AS duplicate_rank
  FROM "public"."documents"
  WHERE canonical_url IS NOT NULL
)
UPDATE "public"."documents" AS document
SET canonical_url = NULL
FROM ranked
WHERE document.id = ranked.id AND ranked.duplicate_rank > 1;

DROP INDEX IF EXISTS "public"."idx_documents_source_url";

CREATE UNIQUE INDEX IF NOT EXISTS "uq_documents_canonical_url"
  ON "public"."documents" ("canonical_url")
  WHERE "canonical_url" IS NOT NULL;

CREATE INDEX IF NOT EXISTS "idx_documents_source_url"
  ON "public"."documents" ("source_url")
  WHERE "source_url" IS NOT NULL;
