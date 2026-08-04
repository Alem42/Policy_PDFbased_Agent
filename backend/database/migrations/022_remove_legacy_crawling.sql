-- Migration 022: remove the unused legacy bulk-crawling subsystem.
-- Firecrawl-backed web search and permanent URL imports use the documents and
-- web_search modules and do not depend on any of these objects.

DROP TABLE IF EXISTS "public"."crawled_document_assets";
DROP TABLE IF EXISTS "public"."crawled_document_versions";
DROP TABLE IF EXISTS "public"."crawl_errors";
DROP TABLE IF EXISTS "public"."crawled_documents";
DROP TABLE IF EXISTS "public"."crawl_jobs";
DROP TABLE IF EXISTS "public"."crawl_sources";

DROP SEQUENCE IF EXISTS "public"."crawl_errors_id_seq";
DROP TYPE IF EXISTS "public"."crawl_job_status";
DROP TYPE IF EXISTS "public"."crawler_preference";
DROP TYPE IF EXISTS "public"."document_status";
