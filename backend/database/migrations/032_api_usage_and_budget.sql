-- One row per paid API request (chat completion, embedding, rerank, web search).
CREATE TABLE IF NOT EXISTS api_usage_events (
    id bigserial PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    provider text NOT NULL,
    model text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('chat', 'embedding', 'rerank', 'web_search')),
    -- area: the feature that triggered it (chat, ingest, evaluation, ...);
    -- operation: the step within it (answer, metadata, evidence_validation, ...).
    area text NOT NULL DEFAULT 'unknown',
    operation text NOT NULL DEFAULT 'unknown',
    user_id uuid REFERENCES app_users(id) ON DELETE SET NULL,
    session_id uuid,
    document_id uuid,
    input_tokens integer NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    output_tokens integer NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    requests integer NOT NULL DEFAULT 1 CHECK (requests >= 0),
    cost_cny numeric(14, 6) NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_api_usage_events_created ON api_usage_events (created_at);
CREATE INDEX IF NOT EXISTS ix_api_usage_events_user ON api_usage_events (user_id, created_at);

-- Budget limits and per-model prices (one JSON row, like the other settings tables).
CREATE TABLE IF NOT EXISTS api_budget_settings (
    id integer PRIMARY KEY CHECK (id = 1),
    config jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT now()
);
