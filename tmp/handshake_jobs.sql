-- handshake_jobs: standalone Handshake source, mirrors jobright_jobs / jobspy_jobs.
-- Run once in the Supabase SQL editor.

create table if not exists public.handshake_jobs (
  id            text primary key,        -- Handshake job id (idempotent upsert key)
  title         text,
  company       text,
  location      text,
  remote        boolean,
  onsite        boolean,
  hybrid        boolean,
  salary        text,
  job_type      text,
  duration      text,
  accepts_opt   boolean,                 -- studentScreen.acceptsOptCandidates
  accepts_cpt   boolean,                 -- studentScreen.acceptsCptCandidates
  sponsors_h1b  boolean,                 -- studentScreen.willingToSponsorCandidate
  apply_url     text,
  role_type     text,                    -- 'intern' | 'newgrad'
  posted_at     timestamptz,
  applied       boolean default false,   -- dashboard toggle; survives re-upserts
  referred      boolean default false,   -- dashboard toggle; survives re-upserts
  dismissed     boolean default false,   -- soft-delete; survives re-upserts
  first_seen    timestamptz default now(),  -- set once on insert (run-divider key)
  updated_at    timestamptz default now()
);

create index if not exists handshake_jobs_posted_idx on public.handshake_jobs (posted_at desc);

-- Same access model as the other job tables: anon key reads, and the
-- scraper/dashboard insert+update (incl. flipping `dismissed`).
alter table public.handshake_jobs enable row level security;

create policy handshake_jobs_select on public.handshake_jobs for select using (true);
create policy handshake_jobs_insert on public.handshake_jobs for insert with check (true);
create policy handshake_jobs_update on public.handshake_jobs for update using (true) with check (true);
