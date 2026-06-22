"""One-time seed of the Supabase config tables from the bundled JSON files.

Idempotent: upserts on each table's unique key, so re-running is safe. Run once
after creating the tables (see the DDL), with SUPABASE_URL / SUPABASE_KEY set:

    ../.venv/bin/python migrate_config.py
"""

import json
import os
import sys
from pathlib import Path

import requests

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


def _upsert(table, rows, on_conflict):
    if not rows:
        return 0
    url, key = os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"]
    r = requests.post(
        f"{url.rstrip('/')}/rest/v1/{table}",
        params={"on_conflict": on_conflict},
        json=rows,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
        timeout=30,
    )
    r.raise_for_status()
    return len(rows)


def main():
    if not (os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_KEY")):
        sys.exit("SUPABASE_URL / SUPABASE_KEY not set")

    targets = json.loads((CONFIG_DIR / "targets.json").read_text())["targets"]
    targets = [{"ats": t["ats"], "slug": t["slug"]} for t in targets if t.get("ats") and t.get("slug")]
    print("targets:", _upsert("targets", targets, "ats,slug"))

    kw = json.loads((CONFIG_DIR / "keywords.json").read_text())
    rows = [{"term": t, "kind": "include"} for t in kw.get("include", [])]
    rows += [{"term": t, "kind": "exclude"} for t in kw.get("exclude", [])]
    print("keywords:", _upsert("keywords", rows, "term,kind"))

    pr = json.loads((CONFIG_DIR / "priority.json").read_text())
    print("priority_companies:", _upsert(
        "priority_companies", [{"name": c} for c in pr.get("allowlist", [])], "name"))
    print("settings:", _upsert(
        "settings", [{"key": "hourly_threshold", "value": str(pr.get("hourly_threshold", 40))}], "key"))


if __name__ == "__main__":
    main()
