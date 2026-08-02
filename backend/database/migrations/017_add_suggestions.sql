-- Migration 017: follow-up question suggestions.
-- Run once against the live database before deploying the new backend code.

-- 1) Admin-tunable suggestion config (one JSON row) — same shape as the other services.
CREATE TABLE IF NOT EXISTS public.suggestion_settings (
    id int NOT NULL DEFAULT 1,
    config jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz(6) NOT NULL DEFAULT now(),
    CONSTRAINT suggestion_settings_pkey PRIMARY KEY (id),
    CONSTRAINT suggestion_settings_singleton CHECK (id = 1)
);

-- 2) Persist the suggestions shown with each assistant message (for history restore).
ALTER TABLE public.chat_messages
    ADD COLUMN IF NOT EXISTS suggestions_json jsonb NOT NULL DEFAULT '[]'::jsonb;

-- 3) Log which suggested questions users click (personalization signal; append-only).
CREATE TABLE IF NOT EXISTS public.suggestion_clicks (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL,
    session_id uuid,
    question text NOT NULL,
    created_at timestamptz(6) NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_suggestion_clicks_user
    ON public.suggestion_clicks (user_id, created_at DESC);
