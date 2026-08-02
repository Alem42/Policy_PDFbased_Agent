-- Migration 011: track web-imported documents for citation/dedup, and add a
-- normalised-content hash for near-duplicate detection ahead of import.
--
-- source_url / imported_by / imported_via record where an imported document
-- came from and who imported it (imported_via distinguishes e.g. "web_search"
-- from any future import path). content_hash is computed after extraction
-- (see documents/service.py process_document) so re-saved/reformatted copies
-- of the same content can be caught even when the raw bytes differ — the
-- existing sha256 column only catches byte-identical duplicates (L1).

ALTER TABLE "public"."documents"
  ADD COLUMN IF NOT EXISTS "source_url" text,
  ADD COLUMN IF NOT EXISTS "imported_by" uuid REFERENCES "public"."app_users"("id") ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS "imported_via" text,
  ADD COLUMN IF NOT EXISTS "content_hash" text;

CREATE INDEX IF NOT EXISTS "idx_documents_source_url"
  ON "public"."documents" ("source_url")
  WHERE "source_url" IS NOT NULL;

CREATE INDEX IF NOT EXISTS "idx_documents_content_hash"
  ON "public"."documents" ("content_hash")
  WHERE "content_hash" IS NOT NULL;
