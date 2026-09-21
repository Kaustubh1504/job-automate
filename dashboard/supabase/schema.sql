-- Mailer schema, multi-tenant. Prefixed mailer_ because this Supabase project
-- is shared with the scraper (`targets`) and the outreach app (`outreach_*`).
-- Apply via the Supabase SQL editor. Safe to re-run.
--
-- Every row is owned by a user_id from Supabase Auth (auth.users). RLS stays
-- disabled to match the rest of the project -- the app is server-only and
-- filters by user_id explicitly on every query.

create table if not exists mailer_people (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  linkedin_url text not null,          -- dedup key, per user
  name text not null,
  email text not null,                 -- pre-verified in the CSV
  title text,
  company text,
  sender_address text not null,        -- sticky: replies land in this mailbox,
                                       -- so follow-ups have to come from it too
  created_at timestamptz default now()
);

create table if not exists mailer_sent (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  person_id uuid references mailer_people(id) on delete set null,
  sender_address text not null,
  subject text not null,
  body text not null,
  status text not null,                -- 'sent' | 'failed'
  error text,
  sent_at timestamptz default now()
);

-- Sending accounts. app_password is AES-256-GCM ciphertext from lib/crypto.ts,
-- never the raw password; the key lives in .env as ENCRYPTION_KEY.
create table if not exists mailer_accounts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  address text not null,
  app_password text not null,
  created_at timestamptz default now()
);

-- === Migration for an install that predates multi-tenancy ===
-- These are no-ops on a fresh database.
alter table mailer_people add column if not exists user_id uuid references auth.users(id) on delete cascade;
alter table mailer_sent   add column if not exists user_id uuid references auth.users(id) on delete cascade;

-- linkedin_url used to be globally unique; it is now unique per user, so two
-- tenants can both hold the same contact.
alter table mailer_people drop constraint if exists mailer_people_linkedin_url_key;

create unique index if not exists mailer_people_user_linkedin_idx
  on mailer_people(user_id, linkedin_url);
create unique index if not exists mailer_accounts_user_address_idx
  on mailer_accounts(user_id, address);
create index if not exists mailer_people_user_company_idx on mailer_people(user_id, company);
create index if not exists mailer_sent_user_idx on mailer_sent(user_id);

alter table mailer_people   disable row level security;
alter table mailer_sent     disable row level security;
alter table mailer_accounts disable row level security;

-- After signing up, claim any rows that predate multi-tenancy:
--   update mailer_people set user_id = '<your-auth-user-id>' where user_id is null;
--   update mailer_sent   set user_id = '<your-auth-user-id>' where user_id is null;
