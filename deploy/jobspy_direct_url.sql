-- Capture jobspy's resolved employer/ATS links on jobspy_jobs. jobspy already
-- fetches these at scrape time (see engine/jobspy_scraper.py); we now persist them.
--   apply_url_direct   : the direct job apply URL on the employer's ATS
--                        (e.g. *.myworkdayjobs.com, *.icims.com). ~100% on Indeed,
--                        empty on LinkedIn. Lets Indeed rows dedup against the
--                        ATS-native boards (Simplify / jobhive / speedyapply) by URL.
--   company_url_direct : the employer's own careers/site URL.
-- Existing rows stay null (populated on the next scrape). Run once in Supabase.
alter table public.jobspy_jobs add column if not exists apply_url_direct   text;
alter table public.jobspy_jobs add column if not exists company_url_direct text;
