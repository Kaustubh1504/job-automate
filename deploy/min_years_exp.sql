-- Years-of-experience bar per job, read out of jobhive's description at scrape
-- time by engine/yoe.py and persisted here instead of the ~5KB JD itself.
--   min_years_exp : the LOWEST year count the posting asks for ("2+ years" -> 2,
--                   "1-3 years" -> 1). NULL means the JD stated none, which is
--                   normal for intern/new-grad postings -- it is not zero.
-- Only jobhive exposes a description (the repo parsers are link aggregators and
-- the authed scrapers return listing metadata), so every other source stays
-- null. Existing rows stay null too: their descriptions were never stored, so
-- there is nothing to backfill from -- the column fills in as jobhive re-scrapes.
-- Run once in Supabase.
alter table public.jobs add column if not exists min_years_exp smallint;

-- Only ~29% of JDs state no number, so the filtered index stays small and the
-- dashboard's "<= 3 yrs" query hits it rather than scanning 48k rows.
create index if not exists jobs_min_years_exp_idx
  on public.jobs (min_years_exp)
  where min_years_exp is not null;
