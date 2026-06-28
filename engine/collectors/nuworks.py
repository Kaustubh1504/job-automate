"""NUworks (Northeastern's Symplicity career portal) collector.

NUworks is login-protected, but its job search is a clean JSON API
(/api/v2/jobs) -- no Cloudflare / SPA, so unlike Handshake there's no stealth
browser. Two things gate it: the session cookies (PHPSESSID + the encrypted
session cookie), and the header `x-requested-system-user: students` (without it
the API returns 200 but total=0). The `authorization: Basic ...` header the
browser sends is NOT needed for reads.

Auth uses the same cURL-paste flow as Handshake: the cookie jar lives in the
shared `sessions` table (refreshed from the dashboard's Sessions box). When the
session lapses the API 401/403s; we flag it expired (one Discord ping) and skip.

The search URL in SOURCES carries the major/school filter (targeted_academic_majors
+ screen_school) and sorts newest-first; this collector fetches just the newest
page (no pagination) -- one request per run keeps the footprint minimal, and the
diff against state catches anything new since the last poll.
"""

import os
import sys
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests

import authsession
from collectors.base import register
from fetcher import config
from listing import Listing

SOURCE = "nuworks"
HOST = "https://northeastern-csm.symplicity.com"
PER_PAGE = 50            # newest 50 only; sort=!postdate puts new roles on top
SYS_USER = "students"    # x-requested-system-user; mandatory for non-empty results


def _alert(msg):
    """One-off Discord ping (the 429 back-off note differs from the expiry one)."""
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        return
    try:
        requests.post(webhook, json={"content": msg}, timeout=15)
    except Exception as e:
        print(f"[nuworks] alert failed: {e}", file=sys.stderr)


def _cookie_header(cookies):
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies)


def _url(base):
    """base search URL with the page params set to fetch the newest PER_PAGE."""
    parts = urlparse(base)
    drop = {"perPage", "page", "json_mode"}
    q = [(k, v) for k, v in parse_qsl(parts.query) if k not in drop]
    q += [("perPage", str(PER_PAGE)), ("page", "1"), ("json_mode", "read_only")]
    return urlunparse(parts._replace(query=urlencode(q)))


def _role_type(job_type):
    # NUworks job_type is a list, e.g. ["Co-op"]. Northeastern's co-ops and
    # internships are the intern bucket; everything else is new-grad.
    t = " ".join(job_type).lower() if isinstance(job_type, list) else str(job_type or "").lower()
    return "intern" if ("co-op" in t or "coop" in t or "intern" in t) else "newgrad"


def _listing(j):
    jid = str(j.get("job_id"))
    loc = j.get("job_location") or ""
    return Listing(
        key=jid,
        company=j.get("name") or "",
        title=j.get("job_title") or "",
        locations=(loc,) if loc else (),
        # Deep link that opens the job in the search panel (the browser's own form).
        url=f"{HOST}/students/app/jobs/search?currentJobId={jid}",
        live=True,
        role_type=_role_type(j.get("job_type")),
    )


@register("nuworks")
def collect(src):
    cookies, status = authsession.load(SOURCE)
    if not cookies:
        print("[nuworks] no session cookies (refresh via dashboard); skipping", file=sys.stderr)
        return []
    headers = {**config.DEFAULT_HEADERS, "Accept": "application/json",
               "Cookie": _cookie_header(cookies), "x-requested-system-user": SYS_USER}

    resp = requests.get(_url(src["url"]), headers=headers, timeout=config.TIMEOUT)
    if resp.status_code in (401, 403):
        print(f"[nuworks] HTTP {resp.status_code} (auth) -> session expired", file=sys.stderr)
        if status != "expired":              # alert once, on the transition
            authsession.alert_expired(SOURCE)
        authsession.save(SOURCE, cookies, "expired", host=HOST)
        return []
    # A rate-limit (429) means the SESSION is fine but we're being pushed back.
    # Hammering through it is what escalates a flag into a ban, so we stop and
    # let the next scheduled run try again -- never retry in-process. Distinct
    # from expiry: don't tell the user to re-paste, just to back off.
    if resp.status_code == 429:
        print("[nuworks] HTTP 429 (rate limited) -> backing off this run", file=sys.stderr)
        if status != "throttled":            # alert once, on the transition
            _alert(f"\U0001f6d1 **NUworks rate-limited (429)** — backing off; the "
                   f"poller will retry next cycle. No action needed (session is fine).")
        authsession.save(SOURCE, cookies, "throttled", host=HOST)
        return []
    resp.raise_for_status()

    out = {}
    for j in resp.json().get("models") or []:
        l = _listing(j)
        out.setdefault(l.key, l)

    print(f"[nuworks] {len(out)} roles (newest {PER_PAGE})", file=sys.stderr)
    if status in ("expired", "throttled"):   # recovered -> clear the flag
        authsession.save(SOURCE, cookies, "active", host=HOST)
    return list(out.values())
