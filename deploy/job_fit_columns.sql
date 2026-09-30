-- Claude Haiku's "is this realistic for 0-3 years of experience" verdict, from
-- engine/llm_fit.py. Written only for newly-seen jobhive rows, after the keyword
-- gate and the state-file dedup (~150 rows/day) -- never for the raw scrape.
--   llm_junior_ok : true/false verdict. NULL means NOT JUDGED (no API key, over
--                   the per-run call ceiling, or the call failed) -- it does not
--                   mean "not a fit". Treat NULL as unknown.
--   llm_reason    : the model's one-line justification, for eyeballing quality.
-- The description itself is never stored; it is read in memory at scrape time
-- and dropped (see engine/collectors/jobhive.py).
-- Run once in Supabase, BEFORE deploying the engine change.
alter table public.jobs add column if not exists llm_junior_ok boolean;
alter table public.jobs add column if not exists llm_reason    text;

-- The New Grad view filters on this, so index the true rows only.
create index if not exists jobs_llm_junior_ok_idx
  on public.jobs (llm_junior_ok)
  where llm_junior_ok is true;
