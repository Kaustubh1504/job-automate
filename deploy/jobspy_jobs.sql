-- JobSpy results table (LinkedIn/Indeed/ZipRecruiter/Google keyword search).
-- Mirrors jobright_jobs: own table, soft-delete via `dismissed`, applied/referred
-- tracking, first_seen for the "seen within" filter. Run once in the Supabase
-- SQL editor. RLS disabled to match the rest of the project.
create table if not exists public.jobspy_jobs (
  id          text primary key,           -- jobspy's own job id (site-prefixed)
  title       text,
  company     text,
  location    text,
  salary      text,
  apply_url   text,
  site        text,                        -- indeed | linkedin | zip_recruiter | google
  job_type    text,
  is_remote   boolean,
  role_type   text,                        -- intern | newgrad
  posted_at   timestamptz,
  first_seen  timestamptz default now(),
  applied     boolean default false,
  referred    boolean default false,
  dismissed   boolean default false
);

alter table public.jobspy_jobs disable row level security;
