#!/usr/bin/env python3
"""Standalone JobSpy scraper -- like jobright.py, intentionally SEPARATE from the
main engine. It aggregates keyword-search results from LinkedIn and Indeed
(via the python-jobspy library) into its own `jobspy_jobs` table and its own
dashboard tab; it does NOT share the Listing format, the cross-source dedup, or
the `jobs` table.

What it does each run, per (role, search term):
  - scrape the boards for recent US roles,
  - upsert the results into `jobspy_jobs` (idempotent on jobspy's own job id),
  - announce only the newly-seen roles to Discord (backlog isn't blasted).

LinkedIn rate-limits hard on a single IP, so it's routed through rotating
residential proxies (JOBSPY_PROXIES) to spread requests across IPs; Indeed works
fine on the host IP and is scraped directly. (ZipRecruiter/Glassdoor were
dropped: their APIs are Cloudflare-WAF-blocked regardless of proxy.)

Run:  .venv/bin/python engine/jobspy_scraper.py
Env:  SUPABASE_URL, SUPABASE_KEY (store; optional -- without them it only prints).
      JOBSPY_PROXIES (optional, comma-separated user:pass@host:port) -- routed to
      LinkedIn only; unset = scrape LinkedIn directly (no behavior change).
"""

import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import requests
from dotenv import find_dotenv, load_dotenv
from jobspy import scrape_jobs

load_dotenv(find_dotenv())

# The shared notifiers/ package lives at the project root (one level up).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import notifiers  # noqa: E402,F401  (importing registers every provider)
from notifiers.base import get_notifier  # noqa: E402
import config_store  # noqa: E402  (engine/ -- centralized title-exclude keywords)
import title_classifier  # noqa: E402  (engine/ -- software-domain title gate + Qwen)

# Per-group scrape settings (each runs as its own jobspy call, per search).
# LinkedIn is proxied (JOBSPY_PROXIES) so we can pull deep without tripping its
# per-IP rate limit. results_wanted=500 = a 50-page budget: it pages until
# LinkedIn runs out (off-season it stops in a few pages), rather than ceiling on
# results_wanted. (jobspy's start<1000 cap still bounds heavy seasons at ~14
# full-page fetches.) 2-day window so postings aren't missed between runs --
# re-fetched rows just upsert (dedup on id; Discord announces only new).
# Indeed works on the host IP and stays lean/fresh.
LINKEDIN = {"sites": ["linkedin"], "results_wanted": 500, "hours_old": 48, "proxied": True}
INDEED = {"sites": ["indeed"], "results_wanted": 50, "hours_old": 24, "proxied": False}
GROUPS = [LINKEDIN, INDEED]

# Discord pings only for intern roles -- matched by title, like the dashboard.
INTERN_RE = re.compile(r"\bintern(ship)?\b", re.I)


def _proxies():
    """JOBSPY_PROXIES (comma-separated user:pass@host:port) -> list, or None.
    Unset means LinkedIn is scraped directly -- no behavior change."""
    raw = os.environ.get("JOBSPY_PROXIES", "").strip()
    return [p.strip() for p in raw.split(",") if p.strip()] or None

# (role_type, indeed/linkedin search_term, google_search_term). Two searches:
# intern and new-grad SWE in the US.
SEARCHES = [
    ("intern",
     '"software engineer" intern',
     "software engineer internship jobs in united states"),
    ("newgrad",
     '"software engineer" ("new grad" OR "entry level")',
     "software engineer new grad jobs in united states"),
]


def _clean(v):
    """pandas NaN/NaT -> None; pass everything else through."""
    if v is None:
        return None
    try:
        if isinstance(v, float) and math.isnan(v):
            return None
    except TypeError:
        pass
    return v


def _salary(r):
    lo, hi, interval = _clean(r.get("min_amount")), _clean(r.get("max_amount")), _clean(r.get("interval"))
    cur = _clean(r.get("currency")) or "USD"
    if not lo and not hi:
        return "N/A"
    span = f"{int(lo):,}-{int(hi):,}" if lo and hi else f"{int(lo or hi):,}"
    return f"{cur} {span}/{interval or 'yr'}"


def _row(role_type, r):
    posted = _clean(r.get("date_posted"))
    return {
        "id": r["id"],
        "title": _clean(r.get("title")),
        "company": _clean(r.get("company")),
        "location": _clean(r.get("location")),
        "salary": _salary(r),
        "apply_url": _clean(r.get("job_url")),
        # The resolved employer/ATS link (e.g. *.myworkdayjobs.com, *.icims.com).
        # jobspy populates this for Indeed (~100%); empty for LinkedIn. Enables
        # dedup against ATS-native boards (Simplify/jobhive/speedyapply) by URL.
        "apply_url_direct": _clean(r.get("job_url_direct")),
        "company_url_direct": _clean(r.get("company_url_direct")),
        "site": _clean(r.get("site")),
        "job_type": _clean(r.get("job_type")),
        "is_remote": bool(_clean(r.get("is_remote"))),
        "role_type": role_type,
        "posted_at": posted.isoformat() if posted else None,
    }


def _scrape(sites, term, google_term, results_wanted, hours_old, proxies):
    return scrape_jobs(
        site_name=sites,
        search_term=term,
        google_search_term=google_term,
        location="United States",
        results_wanted=results_wanted,
        hours_old=hours_old,
        country_indeed="USA",
        proxies=proxies,
        verbose=0,
    )


def scrape():
    """Return {id: row} for all scraped jobs, deduped by jobspy's job id.

    Each GROUP runs as a separate jobspy call (per search) because jobspy applies
    one proxies=/results_wanted=/hours_old= per call: LinkedIn goes through
    JOBSPY_PROXIES with a deep+wide pull, Indeed direct and lean."""
    by_id = {}
    proxies = _proxies()
    _, exclude = config_store.keywords()   # centralized title-exclude (PhD, senior, ...)
    for role_type, term, google_term in SEARCHES:
        for g in GROUPS:
            sites = g["sites"]
            px = proxies if g["proxied"] else None
            try:
                df = _scrape(sites, term, google_term, g["results_wanted"], g["hours_old"], px)
            except Exception as e:
                print(f"[jobspy] {role_type} {sites} scrape failed: {type(e).__name__}: {e}", file=sys.stderr)
                continue
            n = 0
            for _, r in df.iterrows():
                d = r.to_dict()
                if not d.get("id"):
                    continue
                if config_store.excluded(d.get("title"), exclude):  # central title-exclude
                    continue
                by_id.setdefault(d["id"], _row(role_type, d))  # first role wins on overlap
                n += 1
            per_site = df["site"].value_counts().to_dict() if len(df) else {}
            print(f"[jobspy] {role_type} {sites}: {n} rows ({per_site})", file=sys.stderr)
    return by_id


def _dedup_key(row):
    """Stable identity for a role, for deduping announcements. LinkedIn reposts a
    role under a fresh job id every few days, so keying the announce on the id
    re-pings the same role each run; collapse on company+title (normalized)."""
    company = re.sub(r"\s+", " ", (row.get("company") or "").strip().lower())
    title = re.sub(r"\s+", " ", (row.get("title") or "").strip().lower())
    return company, title


def _existing_ids():
    """({id: batch_id}, {dedup_key}) for the rows already in jobspy_jobs, or None
    if we can't tell (no creds / read failed) -- in which case we don't announce,
    to avoid blasting the whole backlog. The id->batch map preserves a re-seen
    row's original run stamp on re-upsert; the dedup-key set makes the announce
    skip roles already seen under any (possibly reposted) id. Paged past
    PostgREST's 1000-row default so the seen-set stays complete as the table grows."""
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if not (url and key):
        return None
    h = {"apikey": key, "Authorization": f"Bearer {key}"}
    id_to_batch, seen, start, step = {}, set(), 0, 1000
    try:
        while True:
            r = requests.get(
                f"{url.rstrip('/')}/rest/v1/jobspy_jobs",
                params={"select": "id,batch_id,company,title"},
                headers={**h, "Range-Unit": "items", "Range": f"{start}-{start + step - 1}"},
                timeout=30,
            )
            if r.status_code == 416:            # asked past the last row -- done
                break
            r.raise_for_status()
            page = r.json()
            if not page:
                break
            for row in page:
                id_to_batch[row["id"]] = row.get("batch_id")
                seen.add(_dedup_key(row))
            if len(page) < step:
                break
            start += step
        return id_to_batch, seen
    except Exception as e:
        print(f"[jobspy] couldn't read existing ids: {e}", file=sys.stderr)
        return None


def save(rows):
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if not (url and key):
        print("[jobspy] Supabase creds not set; skipping store", file=sys.stderr)
        return
    resp = requests.post(
        f"{url.rstrip('/')}/rest/v1/jobspy_jobs",
        params={"on_conflict": "id"},
        json=rows,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
        timeout=60,
    )
    resp.raise_for_status()


def main():
    found = scrape()
    existing = _existing_ids()           # (id->batch, seen dedup keys) or None
    rows = list(found.values())
    print(f"[jobspy] {len(rows)} jobs scraped across {sum(len(g['sites']) for g in GROUPS)} boards")
    # Stamp this run's NEW rows with a shared batch_id so /jobspy?batch=<id> can
    # highlight them; re-seen rows keep their original stamp. Skipped when the
    # seen-set is unknown (existing is None) so we don't clobber stamps blindly.
    batch_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if existing is not None:
        id_to_batch = existing[0]
        for r in rows:
            r["batch_id"] = id_to_batch.get(r["id"], batch_id)
    try:
        save(rows)
    except Exception as e:
        print(f"[jobspy] store failed (does table 'jobspy_jobs' exist?): {e}", file=sys.stderr)

    # Discord: announce only newly-seen INTERN roles (new-grad is stored but not
    # pinged). Dedup on company+title, NOT the job id: LinkedIn reposts a role
    # under a new id every few days, so id-keying re-pings the same role every run.
    # The seen-set is empty/None on the first populated run, so the backlog isn't
    # blasted -- only new postings after.
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if webhook and existing is not None and existing[1]:
        seen = existing[1]
        candidates, announced = [], set()
        for r in rows:
            if not (r.get("title") and INTERN_RE.search(r["title"])):
                continue
            k = _dedup_key(r)
            if k in seen or k in announced:  # seen in a prior run, or a repost within this run
                continue
            announced.add(k)
            candidates.append(r)
        # Software-domain gate -- the same one run.py applies to the un-scoped
        # feeds: keyword include/exclude first, then Qwen classifies the ambiguous
        # rest (cached in title_labels). LinkedIn's fuzzy "software engineer intern"
        # search leaks non-SWE interns (recruiting, marketing, finance); drop them
        # so the intern pings stay software-only. Degrades to the keyword decision
        # when the model is unavailable, so it never blocks the announce.
        inc, exc = config_store.keywords()
        labels = title_classifier.classify(
            [r["title"] for r in candidates
             if title_classifier.ambiguous(r["title"], inc, exc)])
        fresh = [SimpleNamespace(company=r["company"]) for r in candidates
                 if title_classifier.keep(r["title"], inc, exc, labels)]
        print(f"[jobspy] {len(fresh)} new software intern roles since last run", file=sys.stderr)
        try:
            get_notifier("discord")(webhook).send(fresh, header="\U0001f50d **JobSpy** new interns (LinkedIn/Indeed)", path="/jobspy", batch_id=batch_id)
        except Exception as e:
            print(f"[jobspy] discord notify failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
