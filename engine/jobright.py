#!/usr/bin/env python3
"""Standalone jobright.ai minisite scraper -- intentionally SEPARATE from the
main engine. It does NOT share the Listing format, the cross-source dedup, the
poll_all loop, or the `jobs` table; jobright already aggregates roles and tags
H1B sponsorship, so it lives as its own section with its own `jobright_jobs`
table and its own dashboard tab.

What it does each run, per configured minisite:
  - fetch the page, read the 50 most-recent roles from its __NEXT_DATA__ blob,
  - drop jobs that explicitly do NOT sponsor H1B (keep "Yes" and "Not Sure"),
  - upsert the survivors into `jobright_jobs` (idempotent on the jobright id).

Run:  .venv/bin/python engine/jobright.py
Env:  SUPABASE_URL, SUPABASE_KEY (optional -- without them it only prints).
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import requests
from bs4 import BeautifulSoup
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

# The shared notifiers/ package lives at the project root (one level up).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import notifiers  # noqa: E402,F401  (importing registers every provider)
from notifiers.base import get_notifier  # noqa: E402
import config_store  # noqa: E402  (engine/ -- centralized title-exclude keywords)

BASE = "https://jobright.ai/minisites-jobs"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; jobpoll/1.0)"}

# (type, country, category) minisites to poll; each yields the 50 most-recent
# roles (the page server-renders only the newest, no pagination). Add a tuple to
# track another slice.
MINISITES = [
    ("intern", "us", "swe"),
    ("intern", "us", "ml_ai"),
]


def _sponsors_h1b(job):
    """Keep unless H1B sponsorship is an explicit "No". "Not Sure"/"Yes" pass --
    only the hard No is filtered out (jobright marks most roles "Not Sure")."""
    return job.get("h1bSponsored") != "No"


def _is_paid(job):
    """Drop roles explicitly marked "Unpaid". "N/A" (pay not listed) is kept --
    that's unknown pay, not unpaid."""
    return (job.get("salary") or "").strip().lower() != "unpaid"


def _fetch(type_, country, category):
    url = f"{BASE}/{type_}/{country}/{category}"
    html = requests.get(url, headers=HEADERS, timeout=20).text
    node = BeautifulSoup(html, "html.parser").find("script", id="__NEXT_DATA__")
    if not node:
        print(f"[jobright] {category}: no __NEXT_DATA__ on page", file=sys.stderr)
        return []
    return json.loads(node.string)["props"]["pageProps"].get("initialJobs", [])


def scrape():
    """Return {id: (type, category, job_dict)} for all kept jobs, deduped by id."""
    by_id = {}
    _, exclude = config_store.keywords()   # centralized title-exclude (PhD, senior, ...)
    for type_, country, category in MINISITES:
        try:
            jobs = _fetch(type_, country, category)
        except Exception as e:
            print(f"[jobright] {category} fetch failed: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        kept = [j for j in jobs if _sponsors_h1b(j) and _is_paid(j)
                and not config_store.excluded(j.get("title"), exclude)]
        print(f"[jobright] {type_}/{category}: {len(jobs)} fetched, {len(kept)} kept after H1B + paid + keyword filter",
              file=sys.stderr)
        for j in kept:
            by_id[j["id"]] = (type_, category, j)
    return by_id


def _row(type_, category, j):
    posted = j.get("postedDate")
    return {
        "id": j["id"],
        "title": j.get("title"),
        "company": j.get("company"),
        "location": j.get("location"),
        "salary": j.get("salary"),
        "apply_url": j.get("applyUrl"),
        "work_model": j.get("workModel"),
        "h1b_sponsored": j.get("h1bSponsored"),
        "is_new_grad": j.get("isNewGrad"),
        "category": category,
        "role_type": type_,
        "posted_at": datetime.fromtimestamp(posted / 1000, timezone.utc).isoformat() if posted else None,
    }


def _existing_ids():
    """ids already in jobright_jobs (the seen-set used to find new postings), or
    None if we can't tell (no creds / read failed) -- in which case we don't
    announce, to avoid blasting the whole backlog."""
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if not (url and key):
        return None
    try:
        r = requests.get(
            f"{url.rstrip('/')}/rest/v1/jobright_jobs",
            params={"select": "id"},
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=30,
        )
        r.raise_for_status()
        return {row["id"] for row in r.json()}
    except Exception as e:
        print(f"[jobright] couldn't read existing ids: {e}", file=sys.stderr)
        return None


def save(rows):
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if not (url and key):
        print("[jobright] Supabase creds not set; skipping store", file=sys.stderr)
        return
    resp = requests.post(
        f"{url.rstrip('/')}/rest/v1/jobright_jobs",
        params={"on_conflict": "id"},
        json=rows,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
        timeout=30,
    )
    resp.raise_for_status()


def main():
    found = scrape()
    existing = _existing_ids()           # snapshot the seen-set before upserting
    rows = [_row(t, c, j) for (t, c, j) in found.values()]
    for r in rows:
        print(f"  {r['company']} | {r['title']} | h1b={r['h1b_sponsored']} | {r['apply_url']}")
    print(f"[jobright] {len(rows)} jobs kept (H1B-sponsoring or unknown)")
    try:
        save(rows)
    except Exception as e:
        print(f"[jobright] store failed (does table 'jobright_jobs' exist?): {e}", file=sys.stderr)

    # Discord: announce only the newly-seen interns (everything jobright tracks is
    # an intern role). `existing` is empty/None on the first populated run, so the
    # backlog isn't blasted -- only genuinely new postings after that.
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if webhook and existing:
        fresh = [SimpleNamespace(company=j["company"]) for (_, _, j) in found.values()
                 if j["id"] not in existing]
        print(f"[jobright] {len(fresh)} new since last run", file=sys.stderr)
        try:
            get_notifier("discord")(webhook).send(fresh, header="\U0001f7e2 **Jobright interns**")
        except Exception as e:
            print(f"[jobright] discord notify failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
