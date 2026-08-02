-- Migration 018: track LLM token usage per assistant turn, and per ReAct
-- tool-call step within it.
--
-- token_usage: {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}
-- for the whole turn (every LLM call made this turn: each ReAct decision
-- step plus the final answer writer), summed from each AIMessage's
-- usage_metadata. Empty object if the provider never returned usage info.
-- Per-step token counts live inside reasoning_steps (already jsonb, no
-- schema change needed there) as each step's "tokensUsed" field.
-- Run this once against the live database before deploying the new backend code.

ALTER TABLE public.chat_messages
    ADD COLUMN IF NOT EXISTS token_usage jsonb NOT NULL DEFAULT '{}';
