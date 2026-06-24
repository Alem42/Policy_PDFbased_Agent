-- Migrate the initial demo schema to the ingestion-and-cleaning-only schema.
-- This intentionally removes RAG chunks and raw HTML storage.
-- Run in Supabase Dashboard -> SQL Editor after reviewing the backup policy.

begin;

drop function if exists public.match_document_chunks(
  extensions.vector,
  integer,
  double precision,
  uuid
);

drop table if exists public.document_chunks;

alter table public.sources
  add column if not exists max_documents integer;

alter table public.sources
  drop constraint if exists sources_max_documents_check;

alter table public.sources
  add constraint sources_max_documents_check
  check (max_documents is null or max_documents between 1 and 10000);

alter table public.documents
  add column if not exists summary text,
  add column if not exists country text,
  add column if not exists policy_status text,
  add column if not exists start_year integer,
  add column if not exists end_year integer;

alter table public.documents
  drop constraint if exists documents_start_year_check,
  drop constraint if exists documents_end_year_check;

alter table public.documents
  add constraint documents_start_year_check
    check (start_year is null or start_year between 1800 and 2200),
  add constraint documents_end_year_check
    check (end_year is null or end_year between 1800 and 2200);

do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'document_versions'
      and column_name = 'markdown'
  ) and not exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'document_versions'
      and column_name = 'clean_markdown'
  ) then
    alter table public.document_versions
      rename column markdown to clean_markdown;
  end if;
end
$$;

update public.document_versions
set clean_markdown = ''
where clean_markdown is null;

alter table public.document_versions
  alter column clean_markdown set not null,
  drop column if exists raw_html;

create table if not exists public.document_assets (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.documents(id) on delete cascade,
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
  constraint document_assets_document_url_unique
    unique (document_id, original_url)
);

create index if not exists document_assets_document_idx
  on public.document_assets (document_id);

alter table public.document_assets enable row level security;

grant select, insert, update, delete
  on table public.document_assets
  to service_role;

revoke all
  on table public.document_assets
  from anon, authenticated;

commit;
