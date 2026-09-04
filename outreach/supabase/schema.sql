-- Outreach pipeline schema. Tables are prefixed outreach_ because this
-- Supabase project is shared with the scraper (which already owns `targets`).
-- Apply via the Supabase SQL editor. RLS is disabled to match the project
-- (see the `alter table` statements at the bottom) — the app is server-only
-- and uses the anon key, same as the scraper.

create table if not exists outreach_companies (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  email_domain text,
  email_pattern text,              -- e.g. '{first}.{last}'
  created_at timestamptz default now()
);

create table if not exists outreach_people (
  id uuid primary key default gen_random_uuid(),
  linkedin_url text unique not null,   -- dedup key
  name text not null,
  title text,
  company_id uuid references outreach_companies(id),
  email text,
  email_source text,                   -- 'pattern_inferred' | 'manual' | (later) 'hunter'
  email_status text default 'unverified',
  email_confidence numeric,
  created_at timestamptz default now()
);

create table if not exists outreach_campaigns (
  id uuid primary key default gen_random_uuid(),
  jd_text text not null,
  company_id uuid references outreach_companies(id),
  role_title text,
  purpose text not null,               -- 'referral' | 'recruiter_followup' | 'hiring_manager_intro'
  parsed_requirements jsonb,
  followup_interval_days int default 7,    -- clamped to 3..10 in code
  followup_autosend boolean default false, -- false = follow-ups always require approval
  created_at timestamptz default now()
);

create table if not exists outreach_targets (
  id uuid primary key default gen_random_uuid(),
  campaign_id uuid references outreach_campaigns(id),
  person_id uuid references outreach_people(id),
  relevance_score numeric,
  relevance_reason text,               -- one line, LLM-generated
  selected boolean default true,       -- user can toggle off
  unique (campaign_id, person_id)
);

create table if not exists outreach_drafts (
  id uuid primary key default gen_random_uuid(),
  target_id uuid references outreach_targets(id),
  kind text not null default 'initial',   -- 'initial' | 'followup'
  subject text,
  body text,
  rule_check_status text,              -- 'pass' | 'fail'
  rule_failures jsonb,                 -- array of failed rule names + messages
  approved boolean default false,
  scheduled_send_at timestamptz,       -- set at approval; enforces 2-5 min send spacing
  created_at timestamptz default now(),
  unique (target_id, kind)
);

create table if not exists outreach_emails_sent (
  id uuid primary key default gen_random_uuid(),
  target_id uuid references outreach_targets(id),
  gmail_thread_id text,
  gmail_message_id text,
  sent_at timestamptz,
  followup_due_at timestamptz,
  followup_status text default 'scheduled' -- 'scheduled' | 'sent' | 'cancelled' | 'replied'
);

alter table outreach_companies disable row level security;
alter table outreach_people disable row level security;
alter table outreach_campaigns disable row level security;
alter table outreach_targets disable row level security;
alter table outreach_drafts disable row level security;
alter table outreach_emails_sent disable row level security;
