#!/usr/bin/env python3
"""Shared plumbing for login-protected job sources (Handshake, ZipRecruiter,
Glassdoor, NUworks, YC, ...).

One row per source in the Supabase `sessions` table holds the browser cookie jar
+ status. A source scraper: loads the jar, drives a cloakbrowser stealth browser
(headless) that clears Cloudflare, runs its own fetch/parse, then saves the
refreshed jar back. On a login redirect it flags the session expired and pings
Discord; the dashboard refreshes the jar from a pasted cURL.

This module owns only the cross-source concerns (session store, browser launch,
Cloudflare wait, login detection, expiry alert). Each scraper owns its own query
and parsing.
"""

import os
import sys
import time
from datetime import datetime, timezone

import requests
from cloakbrowser import launch_persistent_context

# URL fragments that mean "we got bounced to a login/SSO page".
LOGIN_MARKERS = ("login", "signin", "sign-in", "sign_in", "sso", "/auth/", "session/new")


def _sb():
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    return url, key, {"apikey": key, "Authorization": f"Bearer {key}",
                      "Content-Type": "application/json"}


def load(source):
    """(cookies, status) for `source` from Supabase, or ([], 'active') if none."""
    url, key, h = _sb()
    if not (url and key):
        return [], "active"
    try:
        r = requests.get(f"{url.rstrip('/')}/rest/v1/sessions",
                         params={"select": "cookies,status", "source": f"eq.{source}"},
                         headers=h, timeout=30)
        r.raise_for_status()
        rows = r.json()
        if rows and rows[0].get("cookies"):
            return rows[0]["cookies"], rows[0].get("status", "active")
    except Exception as e:
        print(f"[authsession] load({source}) failed: {e}", file=sys.stderr)
    return [], "active"


def save(source, cookies, status, host=None):
    """Upsert the source's session row (refreshed jar after a run, or expired)."""
    url, key, h = _sb()
    if not (url and key):
        return
    row = {"source": source, "cookies": cookies, "status": status,
           "updated_at": datetime.now(timezone.utc).isoformat()}
    if host:
        row["host"] = host
    try:
        requests.post(f"{url.rstrip('/')}/rest/v1/sessions",
                      params={"on_conflict": "source"}, json=[row],
                      headers={**h, "Prefer": "resolution=merge-duplicates,return=minimal"},
                      timeout=30)
    except Exception as e:
        print(f"[authsession] save({source}) failed: {e}", file=sys.stderr)


def alert_expired(source):
    """One Discord ping on the active->expired transition (caller gates repeats)."""
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        return
    try:
        requests.post(webhook, json={"content":
            f"⚠️ **{source} session expired** — log in to {source}, then in DevTools "
            f"→ Network → Copy as cURL on any request, and paste it into the "
            f"dashboard's *Sessions* box to refresh."}, timeout=15)
    except Exception as e:
        print(f"[authsession] alert({source}) failed: {e}", file=sys.stderr)


def launch(profile_dir, headless=True):
    """A stealth (cloakbrowser) persistent context. Persistent profile = real
    cache/history, which is less bot-like than an ephemeral one."""
    return launch_persistent_context(str(profile_dir), headless=headless)


def clear_cloudflare(page, seconds=45):
    """Poll the local title until the Cloudflare interstitial clears (a real
    browser solves it). No extra network -- title() is local."""
    for _ in range(seconds):
        t = page.title().lower()
        if "just a moment" not in t and "attention required" not in t:
            return
        time.sleep(1)


def looks_like_login(url):
    u = (url or "").lower()
    return any(m in u for m in LOGIN_MARKERS)
