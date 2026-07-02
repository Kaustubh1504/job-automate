-- Resolved ATS/original-posting URL for jobright rows. jobright's public feed
-- only carries the jobright.ai redirect; the underlying employer URL is read from
-- the authenticated job page (see engine/jobright_resolve.py) and stored here so
-- jobright rows can dedup against the ATS-native boards (Indeed/Simplify/jobhive/
-- speedyapply) by URL. Existing rows stay null; filled as the resolver runs. Run
-- once in Supabase.
alter table public.jobright_jobs add column if not exists apply_url_direct text;
