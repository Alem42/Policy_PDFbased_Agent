-- AI Policy Research Platform - PostgreSQL initialization schema.
-- Run once against a fresh PostgreSQL database before enabling DATABASE_ENABLED.

begin;

create extension if not exists pgcrypto;

do $$
begin
  create type public.crawler_preference as enum (
    'auto',
    'http',
    'playwright',
    'firecrawl'
  );
exception
  when duplicate_object then null;
end
$$;

do $$
begin
  create type public.crawl_job_status as enum (
    'pending',
    'running',
    'completed',
    'failed',
    'skipped'
  );
exception
  when duplicate_object then null;
end
$$;

do $$
begin
  create type public.crawled_document_status as enum (
    'active',
    'missing'
  );
exception
  when duplicate_object then null;
end
$$;

create table if not exists public.sources (
  id uuid primary key default gen_random_uuid(),
  name text not null check (char_length(name) between 1 and 200),
  start_url text not null,
  allowed_domains text[] not null default '{}',
  include_patterns text[] not null default '{}',
  exclude_patterns text[] not null default '{}',
  crawler_preference public.crawler_preference not null default 'auto',
  max_pages integer check (max_pages is null or max_pages between 1 and 10000),
  max_documents integer
    check (max_documents is null or max_documents between 1 and 10000),
  max_depth integer not null default 3 check (max_depth between 0 and 20),
  enabled boolean not null default true,
  schedule text,
  config jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint sources_start_url_unique unique (start_url)
);

create table if not exists public.crawl_jobs (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references public.sources(id) on delete cascade,
  dry_run boolean not null default true,
  status public.crawl_job_status not null default 'pending',
  selected_crawler text,
  pages_visited integer not null default 0 check (pages_visited >= 0),
  expected_documents integer check (
    expected_documents is null or expected_documents >= 0
  ),
  pages_discovered integer not null default 0 check (pages_discovered >= 0),
  pages_succeeded integer not null default 0 check (pages_succeeded >= 0),
  pages_failed integer not null default 0 check (pages_failed >= 0),
  documents_added integer not null default 0 check (documents_added >= 0),
  documents_updated integer not null default 0 check (documents_updated >= 0),
  documents_unchanged integer not null default 0 check (documents_unchanged >= 0),
  documents_missing integer not null default 0 check (documents_missing >= 0),
  is_complete boolean,
  message text,
  error_details jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz
);

create table if not exists public.crawled_documents (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references public.sources(id) on delete cascade,
  canonical_url text not null,
  title text,
  summary text,
  country text,
  policy_status text,
  start_year integer check (start_year is null or start_year between 1800 and 2200),
  end_year integer check (end_year is null or end_year between 1800 and 2200),
  content_hash text not null check (char_length(content_hash) = 64),
  current_version integer not null default 1 check (current_version >= 1),
  status public.crawled_document_status not null default 'active',
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  missing_since timestamptz,
  source_published_at timestamptz,
  source_updated_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint crawled_documents_source_url_unique unique (source_id, canonical_url)
);

create table if not exists public.crawled_document_versions (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.crawled_documents(id) on delete cascade,
  crawl_job_id uuid references public.crawl_jobs(id) on delete set null,
  version integer not null check (version >= 1),
  content_hash text not null check (char_length(content_hash) = 64),
  title text,
  clean_markdown text not null,
  metadata jsonb not null default '{}'::jsonb,
  fetched_at timestamptz not null default now(),
  constraint crawled_document_versions_number_unique unique (document_id, version)
);

create table if not exists public.crawled_document_assets (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.crawled_documents(id) on delete cascade,
  asset_type text not null default 'link',
  original_url text not null,
  title text,
  mime_type text,
  is_available boolean,
  http_status integer
    check (http_status is null or http_status between 100 and 599),
  discovered_at timestamptz not null default now(),
  last_checked_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  constraint crawled_document_assets_document_url_unique
    unique (document_id, original_url)
);

create table if not exists public.crawl_errors (
  id bigint generated by default as identity primary key,
  crawl_job_id uuid not null references public.crawl_jobs(id) on delete cascade,
  source_id uuid not null references public.sources(id) on delete cascade,
  url text,
  crawler text,
  error_type text,
  message text not null,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists crawl_jobs_source_created_idx
  on public.crawl_jobs (source_id, created_at desc);

create index if not exists crawl_jobs_status_idx
  on public.crawl_jobs (status);

create index if not exists crawled_documents_source_status_idx
  on public.crawled_documents (source_id, status);

create index if not exists crawled_documents_last_seen_idx
  on public.crawled_documents (last_seen_at desc);

create index if not exists crawled_document_versions_document_fetched_idx
  on public.crawled_document_versions (document_id, fetched_at desc);

create index if not exists crawled_document_assets_document_idx
  on public.crawled_document_assets (document_id);

create index if not exists crawl_errors_job_idx
  on public.crawl_errors (crawl_job_id, created_at);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists sources_set_updated_at on public.sources;
create trigger sources_set_updated_at
before update on public.sources
for each row execute function public.set_updated_at();

drop trigger if exists crawled_documents_set_updated_at on public.crawled_documents;
create trigger crawled_documents_set_updated_at
before update on public.crawled_documents
for each row execute function public.set_updated_at();

commit;
