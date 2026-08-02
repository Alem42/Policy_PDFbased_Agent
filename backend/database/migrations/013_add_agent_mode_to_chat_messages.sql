-- Migration 013: let each turn choose ReAct (multi-step tool-calling agent)
-- vs direct (single retrieval + one-shot answer, no tool loop) mode.
-- Run this once against the live database before deploying the new backend code.

ALTER TABLE public.chat_messages
    ADD COLUMN IF NOT EXISTS agent_mode text NOT NULL DEFAULT 'react';
