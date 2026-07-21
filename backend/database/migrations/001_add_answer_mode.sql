-- Migration 001: Add answer_mode column to chat_messages
-- Run this once against the live database before deploying the new backend code.

ALTER TABLE public.chat_messages
    ADD COLUMN IF NOT EXISTS answer_mode text DEFAULT 'analysis';
