-- Migration 009: provider registry for centrally managed credentials and endpoints.
--
-- Provider rows contain no secrets. API keys remain in the runtime settings
-- store, while model_catalog continues to own provider/model endpoint facts.

CREATE TABLE IF NOT EXISTS public.model_providers (
    id text PRIMARY KEY,
    label text NOT NULL,
    base_url text NOT NULL DEFAULT '',
    is_custom boolean NOT NULL DEFAULT false,
    sort_order int NOT NULL DEFAULT 0,
    created_at timestamptz(6) NOT NULL DEFAULT now(),
    updated_at timestamptz(6) NOT NULL DEFAULT now()
);
