-- Per-run scrape id on the separate board tables, mirroring jobs.batch_id. Each
-- scraper stamps its run's NEW rows with a shared batch_id (compact UTC timestamp)
-- and links its Discord digest to /<board>?batch=<id> so clicking it highlights
-- the roles that run found. Nullable; pre-migration rows stay null. Run once in
-- the Supabase SQL editor BEFORE deploying the updated scrapers.
alter table public.jobright_jobs  add column if not exists batch_id text;
alter table public.jobspy_jobs     add column if not exists batch_id text;
alter table public.handshake_jobs  add column if not exists batch_id text;
alter table public.wellfound_jobs  add column if not exists batch_id text;
