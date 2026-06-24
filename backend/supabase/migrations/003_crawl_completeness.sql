-- Add full-site crawl completeness metrics.

begin;

alter table public.crawl_jobs
  add column if not exists pages_visited integer not null default 0,
  add column if not exists expected_documents integer,
  add column if not exists is_complete boolean;

alter table public.crawl_jobs
  drop constraint if exists crawl_jobs_pages_visited_check,
  drop constraint if exists crawl_jobs_expected_documents_check;

alter table public.crawl_jobs
  add constraint crawl_jobs_pages_visited_check
    check (pages_visited >= 0),
  add constraint crawl_jobs_expected_documents_check
    check (expected_documents is null or expected_documents >= 0);

commit;
