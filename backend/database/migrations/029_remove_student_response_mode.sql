-- Migration 029: retire the Student presentation persona.
-- Preserve existing conversations by mapping their display mode to Researcher.

UPDATE public.chat_sessions
SET response_mode = 'researcher'
WHERE response_mode = 'student';

UPDATE public.chat_messages
SET response_mode = 'researcher'
WHERE response_mode = 'student';

ALTER TABLE public.chat_sessions
    DROP CONSTRAINT IF EXISTS chat_sessions_response_mode_check;

ALTER TABLE public.chat_sessions
    ADD CONSTRAINT chat_sessions_response_mode_check
    CHECK (response_mode IN ('researcher', 'policymaker'));
