-- Migration 014: agent_mode must be nullable
-- Migration 013 made it NOT NULL DEFAULT 'react', but agent_mode is an
-- assistant-only concept (like response_mode/answer_mode/model, which are
-- all nullable) — add_message() never passes it for role='user' rows, so
-- every user message insert violated the NOT NULL constraint.

ALTER TABLE public.chat_messages
    ALTER COLUMN agent_mode DROP NOT NULL;
