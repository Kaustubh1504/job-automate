#!/usr/bin/env python3
"""Standalone JobSpy scraper -- like jobright.py, intentionally SEPARATE from the
main engine. It aggregates keyword-search results from LinkedIn, Indeed
and ZipRecruiter (via the python-jobspy library) into its own
`jobspy_jobs` table and its own dashboard tab; it does NOT share the Listing
format, the cross-source dedup, or the `jobs` table.

What it does each run, per (role, search term):
  - scrape the boards concurrently for recent US roles,
  - upsert the results into `jobspy_jobs` (idempotent on jobspy's own job id),
  - announce only the newly-seen roles to Discord (backlog isn't blasted).

Note: LinkedIn rate-limits hard on a single IP (no proxies configured), so it
usually returns few rows -- Indeed/Google/ZipRecruiter carry the bulk.

Run:  .venv/bin/python engine/jobspy_scraper.py
Env:  SUPABASE_URL, SUPABASE_KEY (optional -- without them it only prints).
"""

import math
import os
import sys
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

SITES = ["indeed", "linkedin", "zip_recruiter"]  # google removed for now
RESULTS_WANTED = 50          # per site, per search
HOURS_OLD = 24               # only roles posted in the last 24 hours

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
        "site": _clean(r.get("site")),
        "job_type": _clean(r.get("job_type")),
        "is_remote": bool(_clean(r.get("is_remote"))),
        "role_type": role_type,
        "posted_at": posted.isoformat() if posted else None,
    }


def scrape():
    """Return {id: row} for all scraped jobs, deduped by jobspy's job id."""
    by_id = {}
    for role_type, term, google_term in SEARCHES:
        try:
            df = scrape_jobs(
                site_name=SITES,
                search_term=term,
                google_search_term=google_term,
                location="United States",
                results_wanted=RESULTS_WANTED,
                hours_old=HOURS_OLD,
                country_indeed="USA",
                verbose=0,
            )
        except Exception as e:
            print(f"[jobspy] {role_type} scrape failed: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        n = 0
        for _, r in df.iterrows():
            d = r.to_dict()
            if not d.get("id"):
                continue
            by_id.setdefault(d["id"], _row(role_type, d))  # first role wins on overlap
            n += 1
        per_site = df["site"].value_counts().to_dict() if len(df) else {}
        print(f"[jobspy] {role_type}: {n} rows ({per_site})", file=sys.stderr)
    return by_id


def _existing_ids():
    """ids already in jobspy_jobs (the seen-set), or None if we can't tell (no
    creds / read failed) -- in which case we don't announce, to avoid blasting
    the whole backlog."""
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if not (url and key):
        return None
    try:
        r = requests.get(
            f"{url.rstrip('/')}/rest/v1/jobspy_jobs",
            params={"select": "id"},
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=30,
        )
        r.raise_for_status()
        return {row["id"] for row in r.json()}
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
    existing = _existing_ids()           # snapshot the seen-set before upserting
    rows = list(found.values())
    print(f"[jobspy] {len(rows)} jobs scraped across {len(SITES)} boards")
    try:
        save(rows)
    except Exception as e:
        print(f"[jobspy] store failed (does table 'jobspy_jobs' exist?): {e}", file=sys.stderr)

    # Discord: announce only the newly-seen roles. `existing` is empty/None on the
    # first populated run, so the backlog isn't blasted -- only new postings after.
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if webhook and existing:
        fresh = [SimpleNamespace(company=r["company"]) for r in rows if r["id"] not in existing]
        print(f"[jobspy] {len(fresh)} new since last run", file=sys.stderr)
        try:
            get_notifier("discord")(webhook).send(fresh, header="\U0001f50d **JobSpy** (LinkedIn/Indeed/ZipRecruiter)")
        except Exception as e:
            print(f"[jobspy] discord notify failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
