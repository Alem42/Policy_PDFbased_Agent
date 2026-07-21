-- Migration 002: Add model column to chat_messages
-- Run this once against the live database before deploying the new backend code.
-- Stores the resolved "<provider>/<model-id>" that actually answered each
-- message (e.g. "openai/gpt-4o"), so chat history can show "Answered by ...".

ALTER TABLE public.chat_messages
    ADD COLUMN IF NOT EXISTS model text;
