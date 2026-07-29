-- Migration 008: model catalog (known provider/model/endpoint reference, no keys).
-- Seeded from code (DEFAULT_CATALOG) on first read; growable via POST /admin/catalog.

CREATE TABLE IF NOT EXISTS public.model_catalog (
    id uuid PRIMARY KEY,
    provider text NOT NULL,
    provider_label text NOT NULL,
    capability text NOT NULL,          -- embedding/rerank plus display-only API categories
    model text NOT NULL,
    base_url text NOT NULL DEFAULT '',
    endpoint text NOT NULL DEFAULT '',
    dimensions int,                    -- embeddings only
    openai_compatible boolean NOT NULL DEFAULT true,
    notes text,
    sort_order int NOT NULL DEFAULT 0,
    created_at timestamptz(6) NOT NULL DEFAULT now(),
    UNIQUE (provider, capability, model)
);
