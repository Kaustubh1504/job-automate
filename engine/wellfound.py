#!/usr/bin/env python3
"""Standalone Wellfound (ex-AngelList Talent) scraper -- SEPARATE from the main
engine, like handshake.py / jobright.py. Its own table (`wellfound_jobs`) and
Discord ping.

Wellfound sits behind DataDome + Cloudflare and requires an authenticated
session, so a plain HTTP request to its GraphQL endpoint gets a 403 captcha
challenge. We drive a real (stealth) browser via cloakbrowser headless: load the
logged-in job feed (which clears the anti-bot challenge under a real browser
fingerprint and fires the site's own `JobSearchResultsX` search query), capture
that request's signed headers (x-apollo-signature / x-wf-cfp), then REPLAY it
from inside the page with our own filter -- software-engineer internships, all
locations, sorted LAST_POSTED -- paging until the results run out.

We replay the page's signed request rather than crafting one because Wellfound
signs each GraphQL operation; reusing the freshly-captured signature lets us
change only the variables (filter/sort/page). The JSON the query returns has
exact post timestamps + clean company/role fields, so it's both more robust and
richer than scraping the SSR'd DOM.

Auth uses a persistent browser profile (wellfound_profile/): the captured
session cookies are seeded from Supabase (table `sessions`, source=wellfound),
then cookies/cache persist across runs. DataDome cookies are short-lived, so
expect to re-paste the cURL via the dashboard more often than the other sources.

Run:  .venv/bin/python engine/wellfound.py
Env:  SUPABASE_URL, SUPABASE_KEY (optional -- without them it only prints).
Deps: cloakbrowser (stealth Chromium; on Linux it needs the chromium system libs).
"""

import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import requests
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import notifiers  # noqa: E402,F401  (registers providers)
from notifiers.base import get_notifier  # noqa: E402

import authsession  # noqa: E402  (engine/ -- shared login-session plumbing)

SOURCE = "wellfound"

HERE = Path(__file__).resolve().parent
HOST = "https://wellfound.com"
LIST_URL = f"{HOST}/jobs"
GRAPHQL_URL = f"{HOST}/graphql"
OP = "JobSearchResultsX"
PROFILE_DIR = HERE / "wellfound_profile"

MAX_PAGES = 5                    # ceiling; stops early when hasNextPage is false
PAGE_PAUSE = (0.8, 2.0)          # human-like gap between page fetches (seconds)

# Wellfound's jobTypes=internship is employer-tagged and noisy (senior roles, even
# a "Certified Medication Aide", come back tagged internship), and roleTagIds
# doesn't hard-filter. So we keep SWE interns client-side: a software
# primaryRoleTitle AND an intern-ish title (which every genuine intern role has).
# Software roles normalize to these categories; mechanical/manufacturing/etc.
# land in "Engineering"/"Other Engineering" and are intentionally excluded.
INTERN_RE = re.compile(r"\b(intern(ship)?|co-?op)\b", re.I)
SOFTWARE_ROLES = {"Software Engineer", "DevOps", "Data Scientist"}


def _is_swe_intern(jl):
    if jl.get("jobType") != "internship" or not jl.get("id"):
        return False
    if (jl.get("primaryRoleTitle") or "") not in SOFTWARE_ROLES:
        return False
    return bool(INTERN_RE.search(jl.get("title") or ""))

# Headers worth forwarding from the page's own signed request (the signature +
# fingerprint are what get us past DataDome on the replay).
_FWD_HEADERS = {
    "content-type", "apollographql-client-name", "apollographql-client-version",
    "x-apollo-operation-name", "x-apollo-signature", "x-wf-cfp",
    "x-requested-with", "apollo-require-preflight",
    "x-angellist-dd-client-referrer-resource",
}

# Run inside the page: POST the signed GraphQL request. Returns {status, data}.
_PAGE_FETCH = """
async ({url, headers, body}) => {
  const r = await fetch(url, {method:'POST', headers, body, credentials:'include'});
  let j; try { j = await r.json(); } catch { j = null; }
  return {status: r.status, data: j};
}
"""


def _posted_at(ts):
    """liveStartAt is unix seconds -> ISO 8601 (or None)."""
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(int(ts), timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def _row(company, jl):
    locs = jl.get("locationNames") or []
    return {
        "id": str(jl.get("id")),
        "title": jl.get("title"),
        "company": company,
        "location": "; ".join(locs) or None,
        "remote": bool(jl.get("remote")),
        "salary": jl.get("compensation") or None,
        "posted_at": _posted_at(jl.get("liveStartAt")),
        "apply_url": f"{HOST}/jobs/{jl.get('id')}-{jl.get('slug') or ''}".rstrip("-"),
        "role_type": "intern",
    }


def _capture_signed_request(page):
    """Let the page fire its own JobSearchResultsX query and grab the signed
    headers + filter. Returns (headers, filter_input, extensions) or (None,..)."""
    cap = {}

    def on_req(r):
        if ("/graphql" in r.url and not cap
                and r.headers.get("x-apollo-operation-name") == OP):
            try:
                pd = json.loads(r.post_data)
            except (TypeError, ValueError):
                return
            cap["headers"] = dict(r.headers)
            cap["filter"] = (pd.get("variables") or {}).get("filterConfigurationInput") or {}
            cap["ext"] = pd.get("extensions")

    page.on("request", on_req)
    # The search XHR fires shortly after the feed renders; nudge with scrolls.
    for _ in range(40):
        if cap:
            break
        try:
            page.evaluate("() => window.scrollBy(0, 700)")
        except Exception:
            pass
        time.sleep(1)
    page.remove_listener("request", on_req)
    return cap.get("headers"), cap.get("filter"), cap.get("ext")


def scrape():
    """Drive cloakbrowser headless on a persistent profile, using the session jar
    from Supabase (source of truth). Returns {id: row}."""
    cookies, status = authsession.load(SOURCE)
    if not cookies:
        print("[wellfound] no session cookies (refresh via dashboard); skipping", file=sys.stderr)
        return {}
    ctx = authsession.launch(PROFILE_DIR)
    try:
        ctx.add_cookies(cookies)                 # Supabase jar is authoritative
        page = ctx.new_page()
        page.goto(LIST_URL, wait_until="domcontentloaded", timeout=60000)
        authsession.clear_cloudflare(page)

        title = (page.title() or "").lower()
        if "captcha" in page.url or "captcha" in title or "datadome" in title:
            print("[wellfound] DataDome challenge not cleared -> throttled", file=sys.stderr)
            if status != "throttled":
                authsession.alert_expired(SOURCE)
            authsession.save(SOURCE, cookies, "throttled", host=HOST)
            return {}
        if authsession.looks_like_login(page.url):
            print("[wellfound] session expired -> login page", file=sys.stderr)
            if status != "expired":          # alert once, on the transition
                authsession.alert_expired(SOURCE)
            authsession.save(SOURCE, cookies, "expired")
            return {}

        headers, captured_filter, ext = _capture_signed_request(page)
        if not headers:
            # Logged in but the search query never fired -> usually a soft block.
            print("[wellfound] never captured a signed search request -> throttled", file=sys.stderr)
            if status != "throttled":
                authsession.alert_expired(SOURCE)
            authsession.save(SOURCE, cookies, "throttled", host=HOST)
            return {}

        fwd = {k: v for k, v in headers.items() if k.lower() in _FWD_HEADERS}
        fwd["content-type"] = "application/json"
        # Keep the session's role tag (software-engineer intern) but drop the
        # location constraints -> SWE interns everywhere, newest first.
        base = dict(captured_filter)
        base.pop("locationTagIds", None)
        base.pop("remoteCompanyLocationTagIds", None)
        base.update({"jobTypes": ["internship"], "sortBy": "LAST_POSTED"})

        by_id = {}
        for p in range(1, MAX_PAGES + 1):
            variables = {"filterConfigurationInput": {**base, "page": p}}
            body = json.dumps({"operationName": OP, "variables": variables, "extensions": ext})
            res = page.evaluate(_PAGE_FETCH, {"url": GRAPHQL_URL, "headers": fwd, "body": body})
            if res["status"] in (401, 403):
                print(f"[wellfound] p{p}: HTTP {res['status']} (auth) -> expired", file=sys.stderr)
                if status != "expired":
                    authsession.alert_expired(SOURCE)
                authsession.save(SOURCE, cookies, "expired")
                return {}
            if res["status"] != 200 or not res.get("data"):
                print(f"[wellfound] p{p}: HTTP {res['status']}, stopping", file=sys.stderr)
                break
            search = (((res["data"].get("data") or {}).get("talent") or {})
                      .get("jobSearchResults") or {})
            edges = (search.get("startups") or {}).get("edges") or []
            new_here = 0
            for e in edges:
                node = e.get("node") or {}
                sr = node.get("promotedStartup") if node.get("__typename") == "PromotedResult" else node
                if not sr or node.get("__typename") == "PromotedResult":
                    continue                       # skip sponsored leak-ins
                company = sr.get("name")
                for jl in sr.get("highlightedJobListings") or []:
                    if not _is_swe_intern(jl):
                        continue
                    if str(jl["id"]) not in by_id:
                        by_id[str(jl["id"])] = _row(company, jl)
                        new_here += 1
            print(f"[wellfound] p{p}: {len(edges)} companies, +{new_here} interns "
                  f"(total {len(by_id)}, hasNext={search.get('hasNextPage')})", file=sys.stderr)
            if not search.get("hasNextPage"):
                break
            time.sleep(random.uniform(*PAGE_PAUSE))

        # refreshed (sliding) session back to Supabase, mark active
        authsession.save(SOURCE, ctx.cookies(), "active", host=HOST)
    finally:
        ctx.close()
    return by_id


def _existing_ids():
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if not (url and key):
        return None
    try:
        r = requests.get(f"{url.rstrip('/')}/rest/v1/wellfound_jobs",
                         params={"select": "id"},
                         headers={"apikey": key, "Authorization": f"Bearer {key}"},
                         timeout=30)
        r.raise_for_status()
        return {row["id"] for row in r.json()}
    except Exception as e:
        print(f"[wellfound] couldn't read existing ids: {e}", file=sys.stderr)
        return None


def save(rows):
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if not (url and key):
        print("[wellfound] Supabase creds not set; skipping store", file=sys.stderr)
        return
    resp = requests.post(
        f"{url.rstrip('/')}/rest/v1/wellfound_jobs",
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
    print(f"[wellfound] {len(rows)} intern roles scraped")
    try:
        save(rows)
    except Exception as e:
        print(f"[wellfound] store failed (does table 'wellfound_jobs' exist?): {e}", file=sys.stderr)

    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if webhook and existing:           # empty/None on first run -> baseline silently
        fresh = [SimpleNamespace(company=r["company"])
                 for r in rows if r["id"] not in existing]
        print(f"[wellfound] {len(fresh)} new intern roles since last run", file=sys.stderr)
        try:
            get_notifier("discord")(webhook).send(
                fresh, header="\U0001f680 **Wellfound** new interns")
        except Exception as e:
            print(f"[wellfound] discord notify failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
