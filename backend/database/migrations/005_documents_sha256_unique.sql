-- Migration 005: prevent exact-duplicate documents (L1 = SHA-256 content hash).
-- Adds a UNIQUE(sha256) constraint so identical-content uploads are rejected at
-- the database level (backstop for the app-side pre-check, closes the race).
--
-- If the ALTER fails because duplicate content already exists, de-duplicate
-- first (keeps the earliest row per hash) and re-run this migration:
--   DELETE FROM documents d USING documents keep
--   WHERE d.sha256 = keep.sha256 AND d.uploaded_at > keep.uploaded_at;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'documents_sha256_key'
    ) THEN
        ALTER TABLE public.documents
            ADD CONSTRAINT documents_sha256_key UNIQUE (sha256);
    END IF;
END $$;
