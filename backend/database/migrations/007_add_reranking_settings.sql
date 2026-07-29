-- Migration 007: admin-tunable reranking configuration.
-- Single JSON row, same shape as embedding_settings. Run once against an
-- existing database; the app defaults if the row is absent.

CREATE TABLE IF NOT EXISTS public.reranking_settings (
    id int PRIMARY KEY DEFAULT 1,
    config jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz(6) NOT NULL DEFAULT now(),
    CONSTRAINT reranking_settings_singleton CHECK (id = 1)
);
