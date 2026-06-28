#!/usr/bin/env python3
"""Poll every configured source and print newly-live roles, aggregated.

Sources are one of two kinds:
  - URL source -> append a SOURCES entry with a `parser` (see parsers/); a
                  conditional GET + ETag fetch is run for it.
  - collector  -> append a SOURCES entry with a `collector` (see collectors/);
                  it acquires its own listings (e.g. jobhive's live ATS scrape).

Schedule with cron using the project venv's Python (jobhive needs >=3.11), e.g.:
    */15 * * * * /Users/kaustubh/Desktop/job-automate/.venv/bin/python \\
        /Users/kaustubh/Desktop/job-automate/engine/run.py >> poll.log 2>&1

Requires: the project venv (requests, python-dotenv, jobhive-py).
Env: GITHUB_TOKEN, loaded from a .env file via find_dotenv().
"""

import dataclasses
import os
import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

# Put the shared project root on the path so the common notifiers/ package
# (one level up, shared across every source repo) is importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import notifiers  # noqa: E402,F401  (importing registers every provider)
import parsers  # noqa: E402,F401  (importing registers every parser)
import collectors  # noqa: E402,F401  (importing registers every collector)
from notifiers.base import get_notifier  # noqa: E402
from poller import poll_all  # noqa: E402
from classify import is_priority  # noqa: E402
from store import SupabaseStore  # noqa: E402
from collectors.jobhive import LAST_RUN_STATS as jobhive_stats  # noqa: E402

load_dotenv(find_dotenv())

RAW = "https://raw.githubusercontent.com"

SOURCES = [
    {"name": "simplify-intern", "role_type": "intern", "parser": "simplify_schema",
     "url": f"{RAW}/SimplifyJobs/Summer2026-Internships/dev/.github/scripts/listings.json"},
    {"name": "vansh-intern", "role_type": "intern", "parser": "simplify_schema",
     "url": f"{RAW}/vanshb03/Summer2026-Internships/dev/.github/scripts/listings.json"},
    {"name": "vansh-2027-intern", "role_type": "intern", "parser": "simplify_schema",
     "url": f"{RAW}/vanshb03/Summer2027-Internships/dev/.github/scripts/listings.json"},
    {"name": "speedyapply-intern", "role_type": "intern", "parser": "speedyapply",
     "url": f"{RAW}/speedyapply/2026-SWE-College-Jobs/main/README.md"},
    # Built In: one centralized national board (country=USA covers every metro);
    # the builtin collector pages through all results. Add a sibling entry per
    # category (engineering, ai-machine-learning, ...) by changing the path.
    {"name": "builtin-engineering", "collector": "builtin",
     "url": "https://builtin.com/jobs/engineering/internship/entry-level?daysSinceUpdated=1&country=USA&allLocations=true"},
    {"name": "builtin-aiml", "collector": "builtin",
     "url": "https://builtin.com/jobs/ai-machine-learning/internship/entry-level?daysSinceUpdated=1&country=USA&allLocations=true"},
    {"name": "simplify-newgrad", "role_type": "newgrad", "parser": "simplify_schema",
     "url": f"{RAW}/SimplifyJobs/New-Grad-Positions/dev/.github/scripts/listings.json"},
    {"name": "vansh-newgrad", "role_type": "newgrad", "parser": "simplify_schema",
     "url": f"{RAW}/vanshb03/New-Grad-2027/dev/.github/scripts/listings.json"},
    # Live per-company ATS scrape (no maintainer lag). Company list + keyword
    # filter live in config/targets.json and config/keywords.json.
    {"name": "jobhive", "collector": "jobhive"},
]
STATE_FILE = Path(__file__).with_name("state.json")


def main():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN not set")

    new = list(poll_all(SOURCES, STATE_FILE, token))
    # Tag the priority flag once so the store and the Discord summary share it.
    new = [dataclasses.replace(l, priority=is_priority(l)) for l in new]

    # Always log to stdout (the cron log keeps the history); also push to Discord
    # if a webhook is configured. A notify failure must not lose the run.
    for listing in new:
        print(f"[{listing.source}] {listing.display()}")

    # Persist first (durable record), then notify. Each sink is failure-isolated
    # so one being down doesn't lose the run or block the other.
    sb_url, sb_key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if sb_url and sb_key:
        try:
            SupabaseStore(sb_url, sb_key).save(new)
        except Exception as e:
            print(f"supabase store failed: {e}", file=sys.stderr)

    # Discord summarizes INTERN roles only (new-grad is still scraped + stored to
    # the dashboard, just not announced here). jobright posts its own intern
    # digest separately (engine/jobright.py).
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if webhook:
        interns = [l for l in new if l.role_type == "intern"]
        try:
            get_notifier("discord")(webhook).send(interns, stats=jobhive_stats)
        except Exception as e:
            print(f"discord notify failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
