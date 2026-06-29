-- wellfound_jobs: standalone Wellfound source, mirrors handshake_jobs.
-- Run once in the Supabase SQL editor.

create table if not exists public.wellfound_jobs (
  id            text primary key,        -- Wellfound job id (idempotent upsert key)
  title         text,
  company       text,
  location      text,
  remote        boolean,
  onsite        boolean,
  hybrid        boolean,
  salary        text,
  posted_at     timestamptz,             -- from the listing's liveStartAt (unix)
  apply_url     text,
  role_type     text,                    -- 'intern'
  applied       boolean default false,   -- dashboard toggle; survives re-upserts
  referred      boolean default false,   -- dashboard toggle; survives re-upserts
  dismissed     boolean default false,   -- soft-delete; survives re-upserts
  first_seen    timestamptz default now(),  -- set once on insert (run-divider key)
  updated_at    timestamptz default now()
);

create index if not exists wellfound_jobs_posted_idx on public.wellfound_jobs (posted_at desc);

-- Same access model as the other job tables: anon key reads, and the
-- scraper/dashboard insert+update (incl. flipping `dismissed`).
alter table public.wellfound_jobs enable row level security;

create policy wellfound_jobs_select on public.wellfound_jobs for select using (true);
create policy wellfound_jobs_insert on public.wellfound_jobs for insert with check (true);
create policy wellfound_jobs_update on public.wellfound_jobs for update using (true) with check (true);
