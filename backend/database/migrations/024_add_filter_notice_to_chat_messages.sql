-- Migration 024: persist the metadata-filter fallback warning per assistant
-- turn so history restores can re-show the yellow "No exact metadata match"
-- banner instead of losing it (the notice used to be prepended to the answer
-- text itself as "Note: ...", which polluted the persisted answer).
--
-- filter_fallback: true when the requested metadata filters could not be
-- satisfied and retrieval expanded back to the original document scope.
-- filter_notice: the user-facing explanation for that expansion.
-- Run this once against the live database before deploying the new backend code.

ALTER TABLE public.chat_messages
    ADD COLUMN IF NOT EXISTS filter_fallback boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS filter_notice text;
