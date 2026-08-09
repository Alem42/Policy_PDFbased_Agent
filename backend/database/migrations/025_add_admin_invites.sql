-- Migration 025: single-use, expiring invitations for administrator registration.

CREATE TABLE IF NOT EXISTS public.admin_invites (
    id uuid PRIMARY KEY,
    code_hash text NOT NULL UNIQUE,
    code_prefix text NOT NULL,
    created_by_user_id uuid REFERENCES public.app_users(id),
    consumed_by_user_id uuid REFERENCES public.app_users(id),
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_admin_invites_created_at
    ON public.admin_invites (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_admin_invites_active
    ON public.admin_invites (expires_at)
    WHERE consumed_at IS NULL AND revoked_at IS NULL;
