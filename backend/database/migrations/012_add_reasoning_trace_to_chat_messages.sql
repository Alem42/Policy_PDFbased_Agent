-- Migration 012: persist the agent's reasoning trace as part of each message
-- Run this once against the live database before deploying the new backend code.
--
-- reasoning_steps: the same tool_call/tool_result step objects the chat UI
-- already renders live (see ChatPage.jsx ReasoningSteps), so history reloads
-- can show the trace that produced a past answer instead of just its text.
-- status: 'streaming' while an assistant turn is still in progress (the row
-- is written the moment the turn starts, then updated after every tool call,
-- so an interrupted/crashed turn leaves a readable partial trace instead of
-- nothing at all), 'complete' once the answer finished, 'error' if it failed.

ALTER TABLE public.chat_messages
    ADD COLUMN IF NOT EXISTS reasoning_steps jsonb NOT NULL DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'complete';
