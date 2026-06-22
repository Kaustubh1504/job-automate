# Setup / Runbook

Job poller + dashboard. The poller scrapes job sources, dedups, classifies
priority, and writes to Supabase + Discord. The dashboard (Vercel) reads/edits
the same Supabase. Read this before changing how it runs.

## Layout
```
job-automate/
├── .env            secrets (gitignored) — see "Env" below
├── .venv/          Python venv, Python >=3.11 (jobhive needs it)
├── config/         JSON configs — now only a FALLBACK; Supabase is source of truth
├── engine/         run.py (entry), poller.py, parsers/, collectors/, classify, store
├── fetcher/        shared HTTP transport (proxies/anti-bot config lives here)
├── notifiers/      Discord output
└── dashboard/      Next.js app (deploy on Vercel)
```

## Run the poller
Always use the venv Python (jobhive needs >=3.11):
```bash
/path/to/job-automate/.venv/bin/python /path/to/job-automate/engine/run.py
```
First run per source baselines (records, reports nothing); later runs report new roles.

## Env (`.env` at repo root, loaded via find_dotenv)
- `GITHUB_TOKEN`        — raises GitHub rate limit for the repo sources
- `SUPABASE_URL`        — project URL
- `SUPABASE_KEY`        — anon/publishable key (read+write to tables)
- `DISCORD_WEBHOOK_URL` — optional; if set, new roles are posted there

## Config = Supabase tables (dashboard-editable)
The poller reads config from Supabase, falling back to `config/*.json` if Supabase
is unreachable/empty.
- `targets`            — {ats, slug, active} companies to scrape
- `keywords`           — {term, kind: include|exclude} title filter
- `priority_companies` — allowlist names for the priority tag
- `settings`           — `hourly_threshold` (priority = salary≥threshold×2080 OR company in allowlist)

Seed Supabase from the JSON files once (idempotent):
```bash
cd engine && ../.venv/bin/python migrate_config.py
```

## Supabase notes
- `jobs` table: `global_id` (unique) is the cross-source dedup key; rows upserted on it.
- RLS is currently **disabled** on all tables ("open for now"). Lock down before sharing anything.
- State (ETags, announced ids, cross-source `_seen`) lives in `engine/state.json` (gitignored).

## Connect to the Pi (SSH)
```bash
ssh <user>@<pi-host-or-ip>      # e.g. ssh pi@raspberrypi.local  or  ssh pi@192.168.1.42
```
Find the IP from your router's device list, or try `ping raspberrypi.local`.

> **Recommended:** set up key auth once with `ssh-copy-id <user>@<pi>` — then no
> password is needed and nothing secret lives in this repo.
>
> **Do not commit the Pi password here** — this file is tracked in git. Keep it in
> a password manager, or (if you want it on this machine) in the gitignored `.env`.
> Fill the connection details below; leave the password out.

- Host / IP: `rpi@kaustubh.local`
- User: `<fill in>`
- Auth: `<ssh key (preferred) | password — store outside git>`

## Cron (Raspberry Pi)
Every 15 min, using the venv Python and absolute paths:
```cron
*/15 * * * * /home/pi/job-automate/.venv/bin/python /home/pi/job-automate/engine/run.py >> /home/pi/job-automate/poll.log 2>&1
```
One full cycle is ~1 min (jobhive scrape dominates; MAX_WORKERS=8 in engine/collectors/jobhive.py).

## Dashboard (Vercel)
- Root Directory = `dashboard/`. Env: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`.
- Local: `cd dashboard && npm install && npm run dev` (needs `dashboard/.env.local` with the same two vars).
