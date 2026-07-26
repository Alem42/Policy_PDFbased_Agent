-- Migration 003: Allow 'policymaker' response_mode in chat_sessions
-- The original constraint only listed 'researcher' and 'student',
-- causing a CHECK violation whenever a policymaker session was created.

ALTER TABLE public.chat_sessions
    DROP CONSTRAINT IF EXISTS chat_sessions_response_mode_check;

ALTER TABLE public.chat_sessions
    ADD CONSTRAINT chat_sessions_response_mode_check
    CHECK (response_mode IN ('researcher', 'policymaker', 'student'));
