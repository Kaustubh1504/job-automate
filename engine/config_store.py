"""Pipeline config (targets, keywords, priority) read from Supabase -- the single
source of truth the dashboard edits.

Each loader queries Supabase and, if that's unreachable or the table is empty,
falls back to the bundled JSON files in config/ so the poller still runs offline
and before the one-time migration. Network/Supabase errors degrade to the file,
they don't crash the poll.
"""

import json
import os
import re
from pathlib import Path

import requests

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


def _rest(table, params):
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if not (url and key):
        raise RuntimeError("Supabase creds not set")
    r = requests.get(
        f"{url.rstrip('/')}/rest/v1/{table}",
        params=params,
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def _json(name):
    return json.loads((CONFIG_DIR / name).read_text())


def targets():
    """[{ats, slug}] of active companies to scrape."""
    try:
        rows = _rest("targets", {"select": "ats,slug", "active": "eq.true"})
        if rows:
            return [{"ats": r["ats"], "slug": r["slug"]} for r in rows]
    except Exception:
        pass
    return [t for t in _json("targets.json")["targets"] if t.get("ats") and t.get("slug")]


def keywords():
    """(include_terms, exclude_terms) for the title filter."""
    try:
        rows = _rest("keywords", {"select": "term,kind"})
        if rows:
            inc = [r["term"] for r in rows if r["kind"] == "include"]
            exc = [r["term"] for r in rows if r["kind"] == "exclude"]
            return inc, exc
    except Exception:
        pass
    cfg = _json("keywords.json")
    return cfg.get("include", []), cfg.get("exclude", [])


def excluded(title, exclude=None):
    """True if `title` contains any centralized exclude term as a whole word
    (case-insensitive). The single title-exclude rule shared by every scraper --
    jobhive, jobright and jobspy -- so the dashboard-editable keyword list governs
    them all. Whole-word (not substring) so "sr" drops "Sr. Engineer" but not
    "SRE", and "staff" doesn't catch "staffing". Pass `exclude` to reuse a list
    already loaded via keywords() and skip a fetch."""
    t = (title or "").lower()
    if exclude is None:
        exclude = keywords()[1]
    return any(re.search(rf"\b{re.escape(x.lower())}\b", t) for x in exclude)


def priority():
    """(hourly_threshold, allowlist_company_names) for the priority tag."""
    try:
        names = [r["name"] for r in _rest("priority_companies", {"select": "name"})]
        srows = _rest("settings", {"select": "value", "key": "eq.hourly_threshold"})
        if names or srows:
            cfg = _json("priority.json")
            threshold = float(srows[0]["value"]) if srows else cfg.get("hourly_threshold", 0)
            return threshold, (names or cfg.get("allowlist", []))
    except Exception:
        pass
    cfg = _json("priority.json")
    return cfg.get("hourly_threshold", 0), cfg.get("allowlist", [])
