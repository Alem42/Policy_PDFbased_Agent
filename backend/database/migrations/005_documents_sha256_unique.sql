-- Migration 005: prevent exact-duplicate documents (L1 = SHA-256 content hash).
-- Adds a UNIQUE(sha256) constraint so identical-content uploads are rejected at
-- the database level (backstop for the app-side pre-check, closes the race).
--
-- If duplicate-content rows already exist this migration aborts with a clear
-- message: resolve them first with the reviewable dedup tool, then re-run.
--   python scripts/dedupe_documents.py            # dry-run report
--   python scripts/dedupe_documents.py --apply    # keep most-complete copy, remove rest
-- (In Docker: docker compose exec backend python scripts/dedupe_documents.py [--apply])

DO $$
DECLARE
    dup_groups int;
BEGIN
    SELECT count(*) INTO dup_groups
    FROM (SELECT sha256 FROM documents GROUP BY sha256 HAVING count(*) > 1) g;

    IF dup_groups > 0 THEN
        RAISE EXCEPTION
            'Cannot add UNIQUE(sha256): % duplicate-content document group(s) exist. '
            'Run scripts/dedupe_documents.py (dry-run) to review, then --apply, then re-run this migration.',
            dup_groups;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'documents_sha256_key') THEN
        ALTER TABLE public.documents ADD CONSTRAINT documents_sha256_key UNIQUE (sha256);
    END IF;
END $$;
