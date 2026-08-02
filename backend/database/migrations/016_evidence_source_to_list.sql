-- Migration 016: an assistant answer can now be backed by more than one
-- evidence tier at once (e.g. a documents-vs-web comparison question), so
-- migration 015's single-value evidence_source text column is replaced with
-- evidence_sources, a jsonb array of tier names ('internal'/'full_corpus'/
-- 'web'), same list-of-strings shape as citations_json/reasoning_steps.
-- Run this once against the live database before deploying the new backend code.

ALTER TABLE public.chat_messages
    DROP COLUMN IF EXISTS evidence_source;

ALTER TABLE public.chat_messages
    ADD COLUMN IF NOT EXISTS evidence_sources jsonb NOT NULL DEFAULT '[]';
