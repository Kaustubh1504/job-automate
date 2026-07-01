-- Per-run scrape id on the main `jobs` table. run.py stamps every row saved in
-- one run with a shared batch_id (a compact UTC timestamp, e.g. 20260701T143000Z);
-- the Discord digest links to /interns?batch=<id> so clicking it highlights the
-- roles that run scraped. Nullable: pre-migration rows and other tables stay null.
-- Run once in the Supabase SQL editor BEFORE deploying the updated engine code.
alter table public.jobs add column if not exists batch_id text;
