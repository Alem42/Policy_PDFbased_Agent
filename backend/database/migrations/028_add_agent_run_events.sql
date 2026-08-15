-- Migration 028: persist sanitized, provider-neutral agent runtime events.
-- Raw prompts, tool arguments, model messages, credentials, and private
-- reasoning are intentionally not represented in this schema.

CREATE TABLE IF NOT EXISTS public.agent_runs (
    run_id text PRIMARY KEY,
    session_id text NOT NULL,
    assistant_message_id text,
    user_id text NOT NULL,
    is_admin boolean NOT NULL DEFAULT false,
    profile jsonb NOT NULL DEFAULT '{}',
    model text,
    prompt_version text NOT NULL,
    configuration_version text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_started_at
    ON public.agent_runs (started_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_runs_session_id
    ON public.agent_runs (session_id, started_at DESC);

CREATE TABLE IF NOT EXISTS public.agent_run_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id text NOT NULL REFERENCES public.agent_runs(run_id) ON DELETE CASCADE,
    sequence integer NOT NULL,
    event_type text NOT NULL,
    occurred_at timestamptz NOT NULL,
    node_name text,
    tool_name text,
    duration_ms double precision,
    token_usage jsonb NOT NULL DEFAULT '{}',
    status text,
    error_type text,
    public_metadata jsonb NOT NULL DEFAULT '{}',
    CONSTRAINT uq_agent_run_events_sequence UNIQUE (run_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_agent_run_events_run_sequence
    ON public.agent_run_events (run_id, sequence);
