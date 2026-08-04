-- Migration 021: verified email registration while preserving legacy users.

ALTER TABLE "public"."app_users"
  ADD COLUMN IF NOT EXISTS "email" text,
  ADD COLUMN IF NOT EXISTS "email_verified_at" timestamptz;

CREATE UNIQUE INDEX IF NOT EXISTS "app_users_email_lower_key"
  ON "public"."app_users" (lower("email")) WHERE "email" IS NOT NULL;

CREATE TABLE IF NOT EXISTS "public"."email_verification_codes" (
  "id" uuid PRIMARY KEY,
  "email" text NOT NULL,
  "code_hash" text NOT NULL,
  "expires_at" timestamptz NOT NULL,
  "consumed_at" timestamptz,
  "attempt_count" integer NOT NULL DEFAULT 0,
  "created_at" timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT "email_verification_attempt_count_check"
    CHECK (attempt_count >= 0)
);

CREATE INDEX IF NOT EXISTS "idx_email_verification_codes_email_created"
  ON "public"."email_verification_codes" (lower("email"), "created_at" DESC);
