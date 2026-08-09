-- Migration 026: registration now collects an email address without verification.

DROP TABLE IF EXISTS public.email_verification_codes;

ALTER TABLE public.app_users
    DROP COLUMN IF EXISTS email_verified_at;
