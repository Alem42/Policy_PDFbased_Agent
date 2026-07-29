-- Migration 006: admin-tunable embedding configuration.
-- Single JSON row so new embedding tunables never need a schema change.
-- Run once against an existing database; the app defaults if the row is absent.

CREATE TABLE IF NOT EXISTS public.embedding_settings (
    id int PRIMARY KEY DEFAULT 1,
    config jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz(6) NOT NULL DEFAULT now(),
    CONSTRAINT embedding_settings_singleton CHECK (id = 1)
);
