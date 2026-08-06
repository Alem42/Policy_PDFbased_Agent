/*
 Navicat Premium Dump SQL

 Source Server         : 9900Demo
 Source Server Type    : PostgreSQL
 Source Server Version : 160014 (160014)
 Source Host           : 20.2.139.148:5432
 Source Catalog        : testdb
 Source Schema         : public

 Target Server Type    : PostgreSQL
 Target Server Version : 160014 (160014)
 File Encoding         : 65001

 Date: 27/06/2026 18:09:25
*/

-- Required extensions managed by PostgreSQL, not by manual CREATE TYPE/FUNCTION blocks
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;
SET search_path = public, pg_catalog;




-- ----------------------------
-- Sequence structure for test_table_id_seq
-- ----------------------------
DROP SEQUENCE IF EXISTS "public"."test_table_id_seq";
CREATE SEQUENCE "public"."test_table_id_seq" 
INCREMENT 1
MINVALUE  1
MAXVALUE 2147483647
START 1
CACHE 1;

-- ----------------------------
-- Table structure for app_users
-- ----------------------------
DROP TABLE IF EXISTS "public"."app_users";
CREATE TABLE "public"."app_users" (
  "id" uuid NOT NULL,
  "uid" text COLLATE "pg_catalog"."default" NOT NULL,
  "username" text COLLATE "pg_catalog"."default" NOT NULL,
  "email" text COLLATE "pg_catalog"."default",
  "email_verified_at" timestamptz(6),
  "password_hash" text COLLATE "pg_catalog"."default" NOT NULL,
  "role" text COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'user'::text,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "updated_at" timestamptz(6) NOT NULL DEFAULT now()
)
;

-- ----------------------------
-- Table structure for email_verification_codes
-- ----------------------------
DROP TABLE IF EXISTS "public"."email_verification_codes";
CREATE TABLE "public"."email_verification_codes" (
  "id" uuid PRIMARY KEY,
  "email" text COLLATE "pg_catalog"."default" NOT NULL,
  "code_hash" text COLLATE "pg_catalog"."default" NOT NULL,
  "expires_at" timestamptz(6) NOT NULL,
  "consumed_at" timestamptz(6),
  "attempt_count" integer NOT NULL DEFAULT 0,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  CONSTRAINT "email_verification_attempt_count_check"
    CHECK (attempt_count >= 0)
)
;

CREATE INDEX "idx_email_verification_codes_email_created"
  ON "public"."email_verification_codes" (lower("email"), "created_at" DESC);
CREATE UNIQUE INDEX "app_users_email_lower_key"
  ON "public"."app_users" (lower("email")) WHERE "email" IS NOT NULL;

-- ----------------------------
-- Table structure for chunk_embeddings
-- ----------------------------
DROP TABLE IF EXISTS "public"."chunk_embeddings";
CREATE TABLE "public"."chunk_embeddings" (
  "chunk_id" uuid NOT NULL,
  "embedding" vector(384) NOT NULL,
  "embedding_model" text COLLATE "pg_catalog"."default" NOT NULL,
  "created_at" timestamptz(6) NOT NULL DEFAULT now()
)
;

-- ----------------------------
-- Table structure for document_chunks
-- ----------------------------
DROP TABLE IF EXISTS "public"."document_chunks";
CREATE TABLE "public"."document_chunks" (
  "id" uuid NOT NULL,
  "document_id" uuid NOT NULL,
  "chunk_index" int4 NOT NULL,
  "page_start" int4 NOT NULL,
  "page_end" int4 NOT NULL,
  "section_title" text COLLATE "pg_catalog"."default",
  "language" text COLLATE "pg_catalog"."default",
  "text" text COLLATE "pg_catalog"."default" NOT NULL,
  "token_count" int4 NOT NULL DEFAULT 0,
  "keywords" text[] COLLATE "pg_catalog"."default" NOT NULL DEFAULT '{}'::text[],
  "metadata_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "created_at" timestamptz(6) NOT NULL DEFAULT now()
)
;

-- ----------------------------
-- Table structure for document_metadata
-- ----------------------------
DROP TABLE IF EXISTS "public"."document_metadata";
CREATE TABLE "public"."document_metadata" (
  "document_id" uuid NOT NULL,
  "title" text COLLATE "pg_catalog"."default",
  "summary" text COLLATE "pg_catalog"."default",
  "source_type" text COLLATE "pg_catalog"."default",
  "source_organisation" text COLLATE "pg_catalog"."default",
  "country_region" text COLLATE "pg_catalog"."default",
  "language" text COLLATE "pg_catalog"."default",
  "year" int4,
  "publication_date" date,
  "policy_areas" text[] COLLATE "pg_catalog"."default" NOT NULL DEFAULT '{}'::text[],
  "keywords" text[] COLLATE "pg_catalog"."default" NOT NULL DEFAULT '{}'::text[],
  "stakeholders" text[] COLLATE "pg_catalog"."default" NOT NULL DEFAULT '{}'::text[],
  "implementation_risks" text[] COLLATE "pg_catalog"."default" NOT NULL DEFAULT '{}'::text[],
  "metadata_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "generated_by_model" text COLLATE "pg_catalog"."default",
  "generated_at" timestamptz(6) NOT NULL DEFAULT now(),
  "reviewed_at" timestamptz(6)
)
;

-- ----------------------------
-- Table structure for document_pages
-- ----------------------------
DROP TABLE IF EXISTS "public"."document_pages";
CREATE TABLE "public"."document_pages" (
  "id" uuid NOT NULL,
  "document_id" uuid NOT NULL,
  "page_number" int4 NOT NULL,
  "text" text COLLATE "pg_catalog"."default" NOT NULL DEFAULT ''::text,
  "char_count" int4 NOT NULL DEFAULT 0,
  "created_at" timestamptz(6) NOT NULL DEFAULT now()
)
;

-- ----------------------------
-- Table structure for policy_taxonomy (admin-editable two-level categories)
-- ----------------------------
CREATE TABLE IF NOT EXISTS "public"."policy_taxonomy" (
  "id" uuid NOT NULL,
  "parent" text COLLATE "pg_catalog"."default" NOT NULL,
  "child" text COLLATE "pg_catalog"."default" NOT NULL,
  "parent_order" int4 NOT NULL DEFAULT 0,
  "child_order" int4 NOT NULL DEFAULT 0,
  "source_ref" text COLLATE "pg_catalog"."default",
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "updated_at" timestamptz(6) NOT NULL DEFAULT now(),
  CONSTRAINT "policy_taxonomy_parent_child_key" UNIQUE ("parent", "child")
)
;

-- ----------------------------
-- Table structure for embedding_settings (admin-tunable embedding config, one JSON row)
-- ----------------------------
CREATE TABLE IF NOT EXISTS "public"."embedding_settings" (
  "id" int4 NOT NULL DEFAULT 1,
  "config" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "updated_at" timestamptz(6) NOT NULL DEFAULT now(),
  CONSTRAINT "embedding_settings_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "embedding_settings_singleton" CHECK ("id" = 1)
)
;

-- ----------------------------
-- Table structure for model_catalog (known provider/model/endpoint reference, no keys)
-- ----------------------------
CREATE TABLE IF NOT EXISTS "public"."model_catalog" (
  "id" uuid NOT NULL,
  "provider" text COLLATE "pg_catalog"."default" NOT NULL,
  "provider_label" text COLLATE "pg_catalog"."default" NOT NULL,
  "capability" text COLLATE "pg_catalog"."default" NOT NULL,
  "model" text COLLATE "pg_catalog"."default" NOT NULL,
  "base_url" text COLLATE "pg_catalog"."default" NOT NULL DEFAULT '',
  "endpoint" text COLLATE "pg_catalog"."default" NOT NULL DEFAULT '',
  "dimensions" int4,
  "openai_compatible" bool NOT NULL DEFAULT true,
  "notes" text COLLATE "pg_catalog"."default",
  "sort_order" int4 NOT NULL DEFAULT 0,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  CONSTRAINT "model_catalog_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "model_catalog_provider_capability_model_key" UNIQUE ("provider", "capability", "model")
)
;

-- ----------------------------
-- Table structure for reranking_settings (admin-tunable reranker config, one JSON row)
-- ----------------------------
CREATE TABLE IF NOT EXISTS "public"."reranking_settings" (
  "id" int4 NOT NULL DEFAULT 1,
  "config" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "updated_at" timestamptz(6) NOT NULL DEFAULT now(),
  CONSTRAINT "reranking_settings_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "reranking_settings_singleton" CHECK ("id" = 1)
)
;

-- ----------------------------
-- Table structure for suggestion_settings (admin-tunable follow-up suggestions, one JSON row)
-- ----------------------------
CREATE TABLE IF NOT EXISTS "public"."suggestion_settings" (
  "id" int4 NOT NULL DEFAULT 1,
  "config" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "updated_at" timestamptz(6) NOT NULL DEFAULT now(),
  CONSTRAINT "suggestion_settings_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "suggestion_settings_singleton" CHECK ("id" = 1)
)
;

-- ----------------------------
-- Table structure for agent_tool_limit_settings (admin-tunable per-tool call budgets for the ReAct agent, one JSON row)
-- ----------------------------
CREATE TABLE IF NOT EXISTS "public"."agent_tool_limit_settings" (
  "id" int4 NOT NULL DEFAULT 1,
  "config" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "updated_at" timestamptz(6) NOT NULL DEFAULT now(),
  CONSTRAINT "agent_tool_limit_settings_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "agent_tool_limit_settings_singleton" CHECK ("id" = 1)
)
;

-- ----------------------------
-- Table structure for suggestion_clicks (which suggested questions users click)
-- ----------------------------
CREATE TABLE IF NOT EXISTS "public"."suggestion_clicks" (
  "id" uuid NOT NULL,
  "user_id" uuid NOT NULL,
  "session_id" uuid,
  "question" text COLLATE "pg_catalog"."default" NOT NULL,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  CONSTRAINT "suggestion_clicks_pkey" PRIMARY KEY ("id")
)
;
CREATE INDEX IF NOT EXISTS "idx_suggestion_clicks_user"
  ON "public"."suggestion_clicks" ("user_id", "created_at" DESC);

-- ----------------------------
-- Table structure for documents
-- ----------------------------
DROP TABLE IF EXISTS "public"."documents";
CREATE TABLE "public"."documents" (
  "id" uuid NOT NULL,
  "original_filename" text COLLATE "pg_catalog"."default" NOT NULL,
  "stored_filename" text COLLATE "pg_catalog"."default" NOT NULL,
  "file_path" text COLLATE "pg_catalog"."default" NOT NULL,
  "file_size" int8 NOT NULL,
  "sha256" text COLLATE "pg_catalog"."default" NOT NULL,
  "mime_type" text COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'application/pdf'::text,
  "status" text COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'uploaded'::text,
  "approved" bool NOT NULL DEFAULT true,
  "access_level" text COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'public'::text,
  "uploaded_at" timestamptz(6) NOT NULL DEFAULT now(),
  "processed_at" timestamptz(6),
  "error_message" text COLLATE "pg_catalog"."default"
)
;

-- ----------------------------
-- Table structure for processing_jobs
-- ----------------------------
DROP TABLE IF EXISTS "public"."processing_jobs";
CREATE TABLE "public"."processing_jobs" (
  "id" uuid NOT NULL,
  "document_id" uuid NOT NULL,
  "job_type" text COLLATE "pg_catalog"."default" NOT NULL,
  "status" text COLLATE "pg_catalog"."default" NOT NULL,
  "started_at" timestamptz(6) NOT NULL DEFAULT now(),
  "finished_at" timestamptz(6),
  "error_message" text COLLATE "pg_catalog"."default",
  "details_json" jsonb NOT NULL DEFAULT '{}'::jsonb
)
;

-- ----------------------------
-- Table structure for test_table
-- ----------------------------
DROP TABLE IF EXISTS "public"."test_table";
CREATE TABLE "public"."test_table" (
  "id" int4 NOT NULL DEFAULT nextval('test_table_id_seq'::regclass),
  "name" varchar(100) COLLATE "pg_catalog"."default" NOT NULL,
  "email" varchar(150) COLLATE "pg_catalog"."default",
  "age" int4,
  "created_at" timestamp(6) DEFAULT CURRENT_TIMESTAMP
)
;

-- ----------------------------
-- Function structure for set_updated_at
-- ----------------------------
DROP FUNCTION IF EXISTS "public"."set_updated_at"();
CREATE FUNCTION "public"."set_updated_at"()
  RETURNS "pg_catalog"."trigger" AS $BODY$
begin
  new.updated_at = now();
  return new;
end;
$BODY$
  LANGUAGE plpgsql VOLATILE
  COST 100
  SET "search_path"="""";

-- ----------------------------
-- Alter sequences owned by
-- ----------------------------
ALTER SEQUENCE "public"."test_table_id_seq"
OWNED BY "public"."test_table"."id";
SELECT setval('"public"."test_table_id_seq"', 1, false);

-- ----------------------------
-- Indexes structure for table app_users
-- ----------------------------
CREATE INDEX "idx_app_users_uid" ON "public"."app_users" USING btree (
  "uid" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

-- ----------------------------
-- Table structure for model_providers (provider registry, no API keys)
-- ----------------------------
CREATE TABLE IF NOT EXISTS "public"."model_providers" (
  "id" text NOT NULL,
  "label" text NOT NULL,
  "base_url" text NOT NULL DEFAULT '',
  "is_custom" boolean NOT NULL DEFAULT false,
  "sort_order" int NOT NULL DEFAULT 0,
  "created_at" timestamptz(6) NOT NULL DEFAULT now(),
  "updated_at" timestamptz(6) NOT NULL DEFAULT now(),
  CONSTRAINT "model_providers_pkey" PRIMARY KEY ("id")
);
CREATE INDEX "idx_app_users_username" ON "public"."app_users" USING btree (
  "username" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

-- ----------------------------
-- Uniques structure for table app_users
-- ----------------------------
ALTER TABLE "public"."app_users" ADD CONSTRAINT "app_users_uid_key" UNIQUE ("uid");
ALTER TABLE "public"."app_users" ADD CONSTRAINT "app_users_username_key" UNIQUE ("username");

-- ----------------------------
-- Checks structure for table app_users
-- ----------------------------
ALTER TABLE "public"."app_users" ADD CONSTRAINT "app_users_role_check" CHECK (role = ANY (ARRAY['admin'::text, 'user'::text]));

-- ----------------------------
-- Primary Key structure for table app_users
-- ----------------------------
ALTER TABLE "public"."app_users" ADD CONSTRAINT "app_users_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table chunk_embeddings
-- ----------------------------
CREATE INDEX "idx_chunk_embeddings_vector" ON "public"."chunk_embeddings" USING hnsw (
  "embedding" "public"."vector_cosine_ops"
);

-- ----------------------------
-- Primary Key structure for table chunk_embeddings
-- ----------------------------
ALTER TABLE "public"."chunk_embeddings" ADD CONSTRAINT "chunk_embeddings_pkey" PRIMARY KEY ("chunk_id");

-- ----------------------------
-- Indexes structure for table document_chunks
-- ----------------------------
CREATE INDEX "idx_document_chunks_document_id" ON "public"."document_chunks" USING btree (
  "document_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);

-- ----------------------------
-- Uniques structure for table document_chunks
-- ----------------------------
ALTER TABLE "public"."document_chunks" ADD CONSTRAINT "document_chunks_document_id_chunk_index_key" UNIQUE ("document_id", "chunk_index");

-- ----------------------------
-- Primary Key structure for table document_chunks
-- ----------------------------
ALTER TABLE "public"."document_chunks" ADD CONSTRAINT "document_chunks_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table document_metadata
-- ----------------------------
CREATE INDEX "idx_document_metadata_keywords" ON "public"."document_metadata" USING gin (
  "keywords" COLLATE "pg_catalog"."default" "pg_catalog"."array_ops"
);
CREATE INDEX "idx_document_metadata_policy_areas" ON "public"."document_metadata" USING gin (
  "policy_areas" COLLATE "pg_catalog"."default" "pg_catalog"."array_ops"
);

-- ----------------------------
-- Primary Key structure for table document_metadata
-- ----------------------------
ALTER TABLE "public"."document_metadata" ADD CONSTRAINT "document_metadata_pkey" PRIMARY KEY ("document_id");

-- ----------------------------
-- Indexes structure for table document_pages
-- ----------------------------
CREATE INDEX "idx_document_pages_document_id" ON "public"."document_pages" USING btree (
  "document_id" "pg_catalog"."uuid_ops" ASC NULLS LAST
);

-- ----------------------------
-- Uniques structure for table document_pages
-- ----------------------------
ALTER TABLE "public"."document_pages" ADD CONSTRAINT "document_pages_document_id_page_number_key" UNIQUE ("document_id", "page_number");

-- ----------------------------
-- Primary Key structure for table document_pages
-- ----------------------------
ALTER TABLE "public"."document_pages" ADD CONSTRAINT "document_pages_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table documents
-- ----------------------------
CREATE INDEX "idx_documents_approved_access" ON "public"."documents" USING btree (
  "approved" "pg_catalog"."bool_ops" ASC NULLS LAST,
  "access_level" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "idx_documents_status" ON "public"."documents" USING btree (
  "status" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

-- ----------------------------
-- Uniques structure for table documents
-- ----------------------------
ALTER TABLE "public"."documents" ADD CONSTRAINT "documents_file_path_key" UNIQUE ("file_path");
-- L1 exact-duplicate guard: reject uploads whose content (SHA-256) already exists.
ALTER TABLE "public"."documents" ADD CONSTRAINT "documents_sha256_key" UNIQUE ("sha256");

-- ----------------------------
-- Primary Key structure for table documents
-- ----------------------------
ALTER TABLE "public"."documents" ADD CONSTRAINT "documents_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Primary Key structure for table processing_jobs
-- ----------------------------
ALTER TABLE "public"."processing_jobs" ADD CONSTRAINT "processing_jobs_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Primary Key structure for table test_table
-- ----------------------------
ALTER TABLE "public"."test_table" ADD CONSTRAINT "test_table_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Foreign Keys structure for table chunk_embeddings
-- ----------------------------
ALTER TABLE "public"."chunk_embeddings" ADD CONSTRAINT "chunk_embeddings_chunk_id_fkey" FOREIGN KEY ("chunk_id") REFERENCES "public"."document_chunks" ("id") ON DELETE CASCADE ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table document_chunks
-- ----------------------------
ALTER TABLE "public"."document_chunks" ADD CONSTRAINT "document_chunks_document_id_fkey" FOREIGN KEY ("document_id") REFERENCES "public"."documents" ("id") ON DELETE CASCADE ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table document_metadata
-- ----------------------------
ALTER TABLE "public"."document_metadata" ADD CONSTRAINT "document_metadata_document_id_fkey" FOREIGN KEY ("document_id") REFERENCES "public"."documents" ("id") ON DELETE CASCADE ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table document_pages
-- ----------------------------
ALTER TABLE "public"."document_pages" ADD CONSTRAINT "document_pages_document_id_fkey" FOREIGN KEY ("document_id") REFERENCES "public"."documents" ("id") ON DELETE CASCADE ON UPDATE NO ACTION;

-- ----------------------------
-- Foreign Keys structure for table processing_jobs
-- ----------------------------
ALTER TABLE "public"."processing_jobs" ADD CONSTRAINT "processing_jobs_document_id_fkey" FOREIGN KEY ("document_id") REFERENCES "public"."documents" ("id") ON DELETE CASCADE ON UPDATE NO ACTION;

-- ----------------------------
-- Table structure for chat_sessions
-- ----------------------------
CREATE TABLE IF NOT EXISTS "public"."chat_sessions" (
  "id"            uuid        NOT NULL DEFAULT gen_random_uuid(),
  "user_id"       uuid        NOT NULL,
  "title"         text        COLLATE "pg_catalog"."default" NOT NULL DEFAULT '',
  "document_ids"  text[]      COLLATE "pg_catalog"."default" NOT NULL DEFAULT '{}',
  "response_mode" text        COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'researcher',
  "created_at"    timestamptz(6) NOT NULL DEFAULT now(),
  "updated_at"    timestamptz(6) NOT NULL DEFAULT now()
);

ALTER TABLE "public"."chat_sessions" ADD CONSTRAINT "chat_sessions_pkey" PRIMARY KEY ("id");

CREATE INDEX IF NOT EXISTS "idx_chat_sessions_user_updated"
  ON "public"."chat_sessions" USING btree ("user_id", "updated_at" DESC);

ALTER TABLE "public"."chat_sessions"
  ADD CONSTRAINT "chat_sessions_user_id_fkey"
  FOREIGN KEY ("user_id") REFERENCES "public"."app_users" ("id") ON DELETE CASCADE;

ALTER TABLE "public"."chat_sessions"
  ADD CONSTRAINT "chat_sessions_response_mode_check"
  CHECK (response_mode IN ('researcher', 'policymaker', 'student'));

-- ----------------------------
-- Table structure for chat_messages
-- ----------------------------
CREATE TABLE IF NOT EXISTS "public"."chat_messages" (
  "id"                  uuid        NOT NULL DEFAULT gen_random_uuid(),
  "session_id"          uuid        NOT NULL,
  "role"                text        COLLATE "pg_catalog"."default" NOT NULL,
  "content"             text        COLLATE "pg_catalog"."default" NOT NULL,
  "citations_json"      jsonb       NOT NULL DEFAULT '[]',
  "evidence_sufficient" bool,
  "response_mode"       text        COLLATE "pg_catalog"."default",
  "answer_mode"         text        COLLATE "pg_catalog"."default" DEFAULT 'analysis',
  "model"               text        COLLATE "pg_catalog"."default",
  "reasoning_steps"     jsonb       NOT NULL DEFAULT '[]',
  "status"              text        COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'complete',
  "agent_mode"          text        COLLATE "pg_catalog"."default" DEFAULT 'react',
  "evidence_sources"    jsonb       NOT NULL DEFAULT '[]',
  "suggestions_json"    jsonb       NOT NULL DEFAULT '[]',
  "token_usage"         jsonb       NOT NULL DEFAULT '{}',
  "filter_fallback"     bool        NOT NULL DEFAULT false,
  "filter_notice"       text        COLLATE "pg_catalog"."default",
  "created_at"          timestamptz(6) NOT NULL DEFAULT now()
);

ALTER TABLE "public"."chat_messages" ADD CONSTRAINT "chat_messages_pkey" PRIMARY KEY ("id");

CREATE INDEX IF NOT EXISTS "idx_chat_messages_session_created"
  ON "public"."chat_messages" USING btree ("session_id", "created_at" ASC);

ALTER TABLE "public"."chat_messages"
  ADD CONSTRAINT "chat_messages_session_id_fkey"
  FOREIGN KEY ("session_id") REFERENCES "public"."chat_sessions" ("id") ON DELETE CASCADE;

ALTER TABLE "public"."chat_messages"
  ADD CONSTRAINT "chat_messages_role_check"
  CHECK (role IN ('user', 'assistant'));

-- ----------------------------
-- Migration 011: web-import tracking + content-hash dedup on documents
-- ----------------------------
ALTER TABLE "public"."documents"
  ADD COLUMN IF NOT EXISTS "source_url" text,
  ADD COLUMN IF NOT EXISTS "imported_by" uuid REFERENCES "public"."app_users"("id") ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS "imported_via" text,
  ADD COLUMN IF NOT EXISTS "content_hash" text;

CREATE INDEX IF NOT EXISTS "idx_documents_source_url"
  ON "public"."documents" ("source_url")
  WHERE "source_url" IS NOT NULL;

CREATE INDEX IF NOT EXISTS "idx_documents_content_hash"
  ON "public"."documents" ("content_hash")
  WHERE "content_hash" IS NOT NULL;

-- Migration 019: concurrency-safe canonical identity for permanent web imports
ALTER TABLE "public"."documents"
  ADD COLUMN IF NOT EXISTS "canonical_url" text;

UPDATE "public"."documents"
SET "canonical_url" = "source_url"
WHERE "canonical_url" IS NULL AND "source_url" IS NOT NULL;

WITH ranked AS (
  SELECT id,
         row_number() OVER (
           PARTITION BY canonical_url
           ORDER BY uploaded_at ASC, id ASC
         ) AS duplicate_rank
  FROM "public"."documents"
  WHERE canonical_url IS NOT NULL
)
UPDATE "public"."documents" AS document
SET canonical_url = NULL
FROM ranked
WHERE document.id = ranked.id AND ranked.duplicate_rank > 1;

DROP INDEX IF EXISTS "public"."idx_documents_source_url";

CREATE UNIQUE INDEX IF NOT EXISTS "uq_documents_canonical_url"
  ON "public"."documents" ("canonical_url")
  WHERE "canonical_url" IS NOT NULL;

CREATE INDEX IF NOT EXISTS "idx_documents_source_url"
  ON "public"."documents" ("source_url")
  WHERE "source_url" IS NOT NULL;

-- Migration 020: lifecycle and review policy for permanent web imports
CREATE TABLE IF NOT EXISTS "public"."web_document_governance" (
  "document_id" uuid PRIMARY KEY REFERENCES "public"."documents"("id") ON DELETE CASCADE,
  "lifecycle_status" text NOT NULL DEFAULT 'active',
  "refresh_interval_days" integer NOT NULL DEFAULT 30,
  "first_imported_at" timestamptz NOT NULL DEFAULT now(),
  "last_fetched_at" timestamptz NOT NULL DEFAULT now(),
  "last_checked_at" timestamptz,
  "next_review_at" timestamptz NOT NULL DEFAULT (now() + interval '30 days'),
  "last_http_status" integer,
  "last_refresh_error" text,
  "content_version" integer NOT NULL DEFAULT 1,
  "created_by" uuid REFERENCES "public"."app_users"("id") ON DELETE SET NULL,
  "created_at" timestamptz NOT NULL DEFAULT now(),
  "updated_at" timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT "web_document_governance_status_check"
    CHECK (lifecycle_status IN ('active', 'stale', 'archived')),
  CONSTRAINT "web_document_governance_interval_check"
    CHECK (refresh_interval_days BETWEEN 1 AND 3650),
  CONSTRAINT "web_document_governance_version_check"
    CHECK (content_version >= 1)
);

CREATE INDEX IF NOT EXISTS "idx_web_document_governance_review"
  ON "public"."web_document_governance" ("lifecycle_status", "next_review_at");

INSERT INTO "public"."web_document_governance" (
  document_id, first_imported_at, last_fetched_at, next_review_at, created_by
)
SELECT id, uploaded_at, uploaded_at, uploaded_at + interval '30 days', imported_by
FROM "public"."documents"
WHERE canonical_url IS NOT NULL
ON CONFLICT (document_id) DO NOTHING;

-- ----------------------------
-- Migration 012: persist the agent's reasoning trace as part of each message
-- ----------------------------
ALTER TABLE public.chat_messages
    ADD COLUMN IF NOT EXISTS reasoning_steps jsonb NOT NULL DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'complete';

-- ----------------------------
-- Migration 013: per-turn ReAct vs direct agent mode
-- (nullable — see migration 014: agent_mode is assistant-only, like
-- response_mode/answer_mode/model, and is null on role='user' rows)
-- ----------------------------
ALTER TABLE public.chat_messages
    ADD COLUMN IF NOT EXISTS agent_mode text DEFAULT 'react';
