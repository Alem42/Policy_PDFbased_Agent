-- Email is contact metadata, not an account identifier. Multiple users may
-- therefore share the same address; usernames remain the unique login key.
DROP INDEX IF EXISTS "public"."app_users_email_lower_key";
