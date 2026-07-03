# job-automate

Personal job-hunt automation: finds software-engineering **intern / co-op / new-grad** roles the moment they go live, so applications go out while postings are hours old — not days.

## How it works

A Python poller (cron on a Raspberry Pi) scrapes many sources each cycle:

- **GitHub repo feeds** — Simplify/vansh internship & new-grad lists, SpeedyApply tables
- **Live ATS scrapes** — ~3,300 tracked companies via jobhive (Greenhouse, Lever, Workday, …), so there's no maintainer lag
- **Job boards** — Built In, LinkedIn/Indeed (JobSpy + proxies), Jobright, Handshake, Wellfound, NUworks (Northeastern co-ops), YC Work at a Startup
- **Browser extension** — polls LinkedIn search in a background tab

Every listing is deduped across sources (canonical ATS URL), filtered to US locations, and gated to software roles — obvious titles by keyword, ambiguous ones by an LLM classifier (Qwen, cached in Supabase). Results are upserted to **Supabase**, new roles are announced to **Discord** (interns only, priority companies starred), and a **Next.js dashboard** (Vercel) is the apply-tracking UI — it also edits the pipeline's config (targets, keywords, priority list, login sessions) live.

## Layout

```
engine/      poller, parsers/, collectors/, standalone scrapers, filters
fetcher/     shared HTTP transport         notifiers/   Discord digests
config/      JSON fallbacks (Supabase is source of truth)
dashboard/   Next.js app                   extension/   WXT browser extension
deploy/      systemd units + table DDL
```

See [SETUP.md](SETUP.md) for the runbook (env, cron, Pi, Supabase tables).
