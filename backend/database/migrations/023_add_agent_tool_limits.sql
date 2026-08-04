-- Migration 023: admin-tunable per-tool call budgets for the ReAct agent.
-- Single JSON row, same shape as reranking_settings/suggestion_settings. Run
-- once against an existing database; the app defaults if the row is absent.

CREATE TABLE IF NOT EXISTS public.agent_tool_limit_settings (
    id int PRIMARY KEY DEFAULT 1,
    config jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz(6) NOT NULL DEFAULT now(),
    CONSTRAINT agent_tool_limit_settings_singleton CHECK (id = 1)
);
