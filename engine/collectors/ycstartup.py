"""YC 'Work at a Startup' (workatastartup.com) collector.

The site's job search is Algolia-backed, so it's a three-step flow:
  1. GET the /companies search page (with the session cookies) -> scrape a FRESH
     Algolia secured key (window.AlgoliaOpts) + the csrf-token meta. Refreshing
     the key every run means we never depend on a pasted/expiring key.
  2. Query the Algolia jobs index (newest-first, filtered to job_type:"intern")
     -> the ordered list of company_ids that have intern roles.
  3. POST those ids to /companies/fetch (cookies + csrf) -> hydrate full company
     data, then keep each company's job_type=="intern" jobs.

Auth uses the same cURL-paste flow as Handshake/NUworks: the cookie jar lives in
the shared `sessions` table. A dead session 401/403s on /companies/fetch (or the
page bounces to login); we flag it expired (one Discord ping) and skip. A 429
means rate-limited -> back off without touching the session.
"""

import json
import os
import re
import sys

import requests

import authsession
from collectors.base import register
from fetcher import config
from listing import Listing

SOURCE = "ycstartup"
HUB = "https://www.workatastartup.com"
ALGOLIA_APP = "45BWZJ1SGC"
INDEX = "WaaSPublicCompanyJob_created_at_desc_production"   # newest-first jobs index
LIST_URL = (HUB + "/companies?demographic=any&hasEquity=any&hasSalary=any&industry=any"
            "&interviewProcess=any&jobType=intern&layout=list-compact&sortBy=created_desc"
            "&tab=any&usVisaNotRequired=any")
HITS_PER_PAGE = 100
FETCH_BATCH = 25
# Algolia params for one page; job_type:"intern" filter, return only company_id.
_ALGOLIA_PARAMS = ("query=&page=%d&filters=(job_type%%3A%%22intern%%22)"
                   "&attributesToRetrieve=%%5B%%22company_id%%22%%5D"
                   "&hitsPerPage=%d&distinct=true")


def _alert(msg):
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        return
    try:
        requests.post(webhook, json={"content": msg}, timeout=15)
    except Exception as e:
        print(f"[ycstartup] alert failed: {e}", file=sys.stderr)


def _cookie_header(cookies):
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies)


def _expired(status):
    print("[ycstartup] session expired", file=sys.stderr)
    if status != "expired":
        authsession.alert_expired(SOURCE)
    authsession.save(SOURCE, _CUR_COOKIES, "expired", host=HUB)


def _company_ids(key):
    """All intern company_ids from Algolia, newest-first, order-preserving dedup."""
    ids, page = [], 0
    while True:
        r = requests.post(
            f"https://{ALGOLIA_APP.lower()}-dsn.algolia.net/1/indexes/*/queries",
            params={"x-algolia-application-id": ALGOLIA_APP, "x-algolia-api-key": key},
            headers={"content-type": "application/x-www-form-urlencoded", "Origin": HUB},
            data=json.dumps({"requests": [{"indexName": INDEX,
                "params": _ALGOLIA_PARAMS % (page, HITS_PER_PAGE)}]}),
            timeout=config.TIMEOUT)
        r.raise_for_status()
        res = r.json()["results"][0]
        ids += [h["company_id"] for h in res.get("hits", [])]
        if page >= res.get("nbPages", 1) - 1:
            break
        page += 1
    return list(dict.fromkeys(ids))


def _listing(company, job):
    loc = job.get("pretty_location_or_remote") or ""
    return Listing(
        key=str(job["id"]),
        company=company.get("name") or "",
        title=job.get("title") or "",
        locations=(loc,) if loc else (),
        url=job.get("show_path") or "",
        live=True,
        role_type="intern",
    )


# Module-level handle so _expired() can re-save the loaded jar (cookies don't
# change across the run; this just stamps status without re-plumbing them).
_CUR_COOKIES = []


@register("ycstartup")
def collect(src):
    global _CUR_COOKIES
    cookies, status = authsession.load(SOURCE)
    if not cookies:
        print("[ycstartup] no session cookies (refresh via dashboard); skipping", file=sys.stderr)
        return []
    _CUR_COOKIES = cookies
    s = requests.Session()
    s.headers.update({"user-agent": config.DEFAULT_HEADERS["User-Agent"],
                      "cookie": _cookie_header(cookies)})

    # 1) page -> fresh Algolia key + csrf
    page = s.get(LIST_URL, headers={"accept": "text/html,application/xhtml+xml"},
                 timeout=config.TIMEOUT)
    if page.status_code in (401, 403) or authsession.looks_like_login(page.url):
        _expired(status)
        return []
    km = re.search(r'window\.AlgoliaOpts\s*=\s*(\{.*?\});', page.text, re.S)
    cm = re.search(r'<meta name="csrf-token" content="([^"]*)"', page.text)
    if not (km and cm):                      # logged-out page has no key/csrf
        _expired(status)
        return []
    key = json.loads(km.group(1))["key"]
    csrf = cm.group(1)

    # 2) Algolia -> ordered intern company_ids
    ids = _company_ids(key)

    # 3) hydrate in batches -> intern jobs
    out = {}
    for i in range(0, len(ids), FETCH_BATCH):
        r = s.post(HUB + "/companies/fetch",
                   headers={"accept": "application/json", "content-type": "application/json",
                            "origin": HUB, "x-csrf-token": csrf,
                            "x-requested-with": "XMLHttpRequest"},
                   data=json.dumps({"ids": ids[i:i + FETCH_BATCH]}), timeout=config.TIMEOUT)
        if r.status_code in (401, 403):
            _expired(status)
            return []
        if r.status_code == 429:
            print("[ycstartup] HTTP 429 (rate limited) -> backing off this run", file=sys.stderr)
            if status != "throttled":
                _alert("\U0001f6d1 **YC startups rate-limited (429)** — backing off; the "
                       "poller will retry next cycle. No action needed (session is fine).")
            authsession.save(SOURCE, cookies, "throttled", host=HUB)
            return []
        r.raise_for_status()
        for c in r.json().get("companies", []):
            for j in c.get("jobs", []):
                if j.get("job_type") == "intern" and j.get("id"):
                    l = _listing(c, j)
                    out.setdefault(l.key, l)

    print(f"[ycstartup] {len(out)} intern roles across {len(ids)} companies", file=sys.stderr)
    if status in ("expired", "throttled"):
        authsession.save(SOURCE, cookies, "active", host=HUB)
    return list(out.values())
