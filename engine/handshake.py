#!/usr/bin/env python3
"""Standalone Handshake (university job board) scraper -- intentionally SEPARATE
from the main engine, like jobright.py / jobspy_scraper.py. Its own table
(`handshake_jobs`) and dashboard tab.

Handshake sits behind Cloudflare and requires an authenticated session, so a
plain HTTP request gets a 403 challenge. We drive a real (stealth) browser via
cloakbrowser headless: load the job-search page (which clears the Cloudflare
challenge and yields a fresh CSRF token), then run the site's own GraphQL query
from inside the page for each search, paging up to MAX_PAGES.

Auth uses a persistent browser profile (handshake_profile/): the captured session
cookies are seeded into it once on first run, then cookies/localStorage/cache
persist across runs automatically. Handshake's session is sliding, so regular runs
keep it alive without re-grabbing cookies; a real (non-ephemeral) profile also
looks less bot-like to Cloudflare. If the session fully lapses we land on the
login page and skip (delete the profile + refresh handshake_cookies.json to
re-seed, or log in once headed).

Run:  .venv/bin/python engine/handshake.py
Env:  SUPABASE_URL, SUPABASE_KEY (optional -- without them it only prints).
Deps: cloakbrowser (stealth Chromium; on Linux it needs the chromium system libs).
"""

import json
import os
import random
import sys
import time
from base64 import b64encode
from pathlib import Path
from types import SimpleNamespace

import requests
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import notifiers  # noqa: E402,F401  (registers providers)
from notifiers.base import get_notifier  # noqa: E402

import authsession  # noqa: E402  (engine/ -- shared login-session plumbing)

SOURCE = "handshake"

HERE = Path(__file__).resolve().parent
HOST = "https://northeastern.joinhandshake.com"
GRAPHQL_URL = f"{HOST}/hs/graphql"
QUERY = json.loads((HERE / "handshake_query.json").read_text())
COOKIES_FILE = HERE / "handshake_cookies.json"   # seed only; profile persists after
PROFILE_DIR = HERE / "handshake_profile"

PER_PAGE = 50
MAX_PAGES = 3                     # ceiling per search; stops early when exhausted
PAGE_PAUSE = (1.0, 3.0)           # human-like gap between page fetches (seconds)

# (role_type, search query) -- one navigation per search, then paged GraphQL.
SEARCHES = [
    ("intern", "software ai ml intern"),
    ("newgrad", "software engineer new grad"),
]

# Discord pings only for intern roles, matched by title (search buckets are noisy).
import re  # noqa: E402
INTERN_RE = re.compile(r"\bintern(ship)?\b", re.I)


def _cursor(offset):
    """Handshake's relay cursor is base64 of the integer offset ('MA==' == '0')."""
    return b64encode(str(offset).encode()).decode()


def _body(query, after):
    variables = {"first": PER_PAGE, "after": after,
                 "input": {"filter": {"query": query},
                           "sort": {"direction": "DESC", "field": "POST_DATE"},
                           "channel": "NL_SEARCH_CHANNEL"}}
    return json.dumps({"operationName": QUERY["operationName"],
                       "variables": variables, "query": QUERY["query"]})


def _salary(job):
    rng = job.get("salaryRange") or {}
    lo, hi, cur = rng.get("min"), rng.get("max"), rng.get("currency") or "USD"
    sched = ((rng.get("paySchedule") or {}).get("friendlyName")
             or (job.get("salaryType") or {}).get("name") or "")
    if not lo and not hi:
        return None
    span = f"{int(lo):,}-{int(hi):,}" if lo and hi else f"{int(lo or hi):,}"
    return f"{cur} {span} {sched}".strip()


def _row(role_type, node):
    job = node.get("job") or {}
    ss = job.get("studentScreen") or {}
    locs = [l.get("displayName") or l.get("name") for l in (job.get("locations") or [])]
    posted = job.get("applyStart") or job.get("createdAt")
    return {
        "id": str(job.get("id")),
        "title": job.get("title"),
        "company": (job.get("employer") or {}).get("name"),
        "location": "; ".join(l for l in locs if l) or None,
        "remote": bool(job.get("remote")),
        "onsite": bool(job.get("onSite")),
        "hybrid": bool(job.get("hybrid")),
        "salary": _salary(job),
        "job_type": (job.get("jobType") or {}).get("name"),
        "duration": job.get("duration"),
        "accepts_opt": ss.get("acceptsOptCandidates"),
        "accepts_cpt": ss.get("acceptsCptCandidates"),
        "sponsors_h1b": ss.get("willingToSponsorCandidate"),
        "apply_url": f"{HOST}/jobs/{job.get('id')}",
        "role_type": role_type,
        "posted_at": posted,
    }


# Run inside the page: POST the GraphQL query with the page's own cookies + a
# fresh CSRF token. Returns {status, data}.
_PAGE_FETCH = """
async ({url, headers, body}) => {
  const r = await fetch(url, {method:'POST', headers, body, credentials:'include'});
  let j; try { j = await r.json(); } catch { j = null; }
  return {status: r.status, data: j};
}
"""


def scrape():
    """Drive cloakbrowser headless on a persistent profile, using the session jar
    from Supabase (source of truth). Returns {id: row} deduped across searches."""
    by_id = {}
    cookies, status = authsession.load(SOURCE)
    if not cookies and COOKIES_FILE.exists():        # first-time bootstrap seed
        cookies = json.loads(COOKIES_FILE.read_text())
    if not cookies:
        print("[handshake] no session cookies (refresh via dashboard); skipping", file=sys.stderr)
        return {}
    ctx = authsession.launch(PROFILE_DIR)
    try:
        ctx.add_cookies(cookies)                 # Supabase jar is authoritative
        page = ctx.new_page()
        # one navigation to clear Cloudflare + read a session-matching CSRF token
        first_url = (f"{HOST}/job-search?query={SEARCHES[0][1].replace(' ', '+')}"
                     f"&per_page={PER_PAGE}&sort=posted_date_desc&page=1")
        page.goto(first_url, wait_until="domcontentloaded", timeout=60000)
        authsession.clear_cloudflare(page)
        if authsession.looks_like_login(page.url):
            print("[handshake] session expired -> login page", file=sys.stderr)
            if status != "expired":          # alert once, on the transition
                authsession.alert_expired(SOURCE)
            authsession.save(SOURCE, cookies, "expired")
            return {}
        csrf = page.evaluate(
            "() => document.querySelector('meta[name=\\\"csrf-token\\\"]')?.content || ''")
        headers = {
            "accept": "*/*", "content-type": "application/json",
            "apollographql-client-name": "consumer",
            "apollographql-client-version": "1.2",
            "graphql-operation-type": "query",
            "x-csrf-token": csrf,
        }
        for role_type, query in SEARCHES:
            for p in range(MAX_PAGES):
                res = page.evaluate(_PAGE_FETCH, {
                    "url": GRAPHQL_URL, "headers": headers,
                    "body": _body(query, _cursor(p * PER_PAGE))})
                if res["status"] != 200 or not res.get("data"):
                    print(f"[handshake] {role_type} p{p+1}: HTTP {res['status']}", file=sys.stderr)
                    break
                js = (res["data"].get("data") or {}).get("jobSearch") or {}
                edges = js.get("edges") or []
                for e in edges:
                    node = e.get("node") or {}
                    if node.get("job", {}).get("id"):
                        by_id.setdefault(str(node["job"]["id"]), _row(role_type, node))
                print(f"[handshake] {role_type} p{p+1}: {len(edges)} edges "
                      f"(total={js.get('totalCount')})", file=sys.stderr)
                if len(edges) < PER_PAGE:        # last page for this search
                    break
                time.sleep(random.uniform(*PAGE_PAUSE))
        # write the refreshed (sliding) session back to Supabase, mark active
        authsession.save(SOURCE, ctx.cookies(), "active", host=HOST)
    finally:
        ctx.close()
    return by_id


def _existing_ids():
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if not (url and key):
        return None
    try:
        r = requests.get(f"{url.rstrip('/')}/rest/v1/handshake_jobs",
                         params={"select": "id"},
                         headers={"apikey": key, "Authorization": f"Bearer {key}"},
                         timeout=30)
        r.raise_for_status()
        return {row["id"] for row in r.json()}
    except Exception as e:
        print(f"[handshake] couldn't read existing ids: {e}", file=sys.stderr)
        return None


def save(rows):
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if not (url and key):
        print("[handshake] Supabase creds not set; skipping store", file=sys.stderr)
        return
    resp = requests.post(
        f"{url.rstrip('/')}/rest/v1/handshake_jobs",
        params={"on_conflict": "id"},
        json=rows,
        headers={"apikey": key, "Authorization": f"Bearer {key}",
                 "Content-Type": "application/json",
                 "Prefer": "resolution=merge-duplicates,return=minimal"},
        timeout=60,
    )
    resp.raise_for_status()


def main():
    found = scrape()
    existing = _existing_ids()           # snapshot before upserting
    rows = list(found.values())
    print(f"[handshake] {len(rows)} roles scraped")
    try:
        save(rows)
    except Exception as e:
        print(f"[handshake] store failed (does table 'handshake_jobs' exist?): {e}", file=sys.stderr)

    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if webhook and existing:
        fresh = [SimpleNamespace(company=r["company"]) for r in rows
                 if r["id"] not in existing and r.get("title") and INTERN_RE.search(r["title"])]
        print(f"[handshake] {len(fresh)} new intern roles since last run", file=sys.stderr)
        try:
            get_notifier("discord")(webhook).send(
                fresh, header="\U0001f393 **Handshake** new interns")
        except Exception as e:
            print(f"[handshake] discord notify failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
