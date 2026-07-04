# job-automate

Personal job-hunt automation: finds software-engineering **intern / co-op / new-grad** roles the moment they go live, so applications go out while postings are hours old — not days.

Everything runs 24/7 on a **Raspberry Pi**: each source group has its own systemd timer (`deploy/`) with a jittered, human-like cadence — the fast repo/board poll hourly, the big jobhive ATS sweep every 2h on its own timer so it can't delay the fast poll, and the authed/anti-bot sources (Handshake, Wellfound, NUworks, YC, Jobright) every 30 min-3h at randomized offsets. The Pi keeps per-source state files, so restarts never re-announce old roles.

## Sources monitored

| Source | What it is |
| --- | --- |
| **Company ATSes (jobhive)** | **~3,300 monitored companies** scraped live (Greenhouse, Lever, Ashby, Workday, iCIMS, …) — a posting is caught the moment the company publishes it, no maintainer lag; list is dashboard-editable |
| **Simplify** | Summer internships + New-Grad-Positions GitHub feeds |
| **vansh** | Summer 2026/2027 internships + New-Grad-2027 GitHub feeds |
| **SpeedyApply** | 2026 SWE college-jobs tables (GitHub) |
| **Built In** | national board, engineering + AI/ML categories |
| **LinkedIn** | JobSpy guest-API search (proxied) + browser-extension search polling |
| **Indeed** | JobSpy search, direct |
| **Jobright.ai** | SWE + AI/ML intern minisites, with H1B-sponsorship tags and authed ATS-link resolution |
| **Handshake** | university board, authed stealth-browser GraphQL |
| **Wellfound** | (ex-AngelList) startup board, authed signed-request replay |
| **NUworks** | Northeastern's Symplicity portal — co-ops, the top-priority source |
| **YC Work at a Startup** | every intern role across YC startups, Algolia-backed |

**Proxies:** LinkedIn rate-limits hard per IP, so JobSpy routes it through rotating residential proxies (`JOBSPY_PROXIES`) and pages deep on guest URLs; Indeed works fine direct. ZipRecruiter/Glassdoor were dropped — Cloudflare WAF blocks them regardless of proxy. Cloudflare-gated authed sources (Handshake, Wellfound) use a stealth headless browser on a persistent profile instead.

Every listing is deduped across sources (canonical ATS URL), filtered to US locations, and gated to software roles — obvious titles by keyword, ambiguous ones by an LLM classifier (Qwen, cached in Supabase).

**Discord:** each run posts a per-company digest of newly-seen **intern** roles only (the backlog is never blasted — first runs just baseline). Priority companies (FAANG+/quant allowlist or salary above threshold) are starred first, every digest deep-links to that scrape's rows on the dashboard (`?batch=`), NUworks/YC get their own color-coded embeds, and expired login sessions ping once with re-paste instructions.

Results are upserted to **Supabase**, and a **Next.js dashboard** (Vercel) is the apply-tracking UI — it also edits the pipeline's config (targets, keywords, priority list, login sessions) live.

## Layout

```
engine/      poller, parsers/, collectors/, standalone scrapers, filters
fetcher/     shared HTTP transport         notifiers/   Discord digests
config/      JSON fallbacks (Supabase is source of truth)
dashboard/   Next.js app                   extension/   WXT browser extension
deploy/      systemd units + table DDL
```

See [SETUP.md](SETUP.md) for the runbook (env, cron, Pi, Supabase tables).
