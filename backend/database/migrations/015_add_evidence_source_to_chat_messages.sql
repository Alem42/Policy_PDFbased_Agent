-- Migration 015: track which retrieval tier actually produced the evidence
-- behind a ReAct chat answer ('internal' selected documents, 'full_corpus'
-- library-wide search, or 'web' search), so the frontend can render a
-- distinct style per source instead of treating every cited answer the
-- same way. NULL means no tier was sufficient this turn (Open Discussion
-- general-knowledge fallback or a Document Analysis refusal).
-- Run this once against the live database before deploying the new backend code.

ALTER TABLE public.chat_messages
    ADD COLUMN IF NOT EXISTS evidence_source text;
