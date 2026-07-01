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
from datetime import datetime, timezone
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
import config_store  # noqa: E402
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
]

# jobhive (the live per-company ATS scrape, no maintainer lag) runs on its OWN
# timer via `run.py jobhive`. The ~3,300-company scrape is slow, so isolating it
# keeps the fast repo/Built In poll above from timing out -- and from discarding
# its results if jobhive overruns. Company list + filter live in
# config/targets.json and config/keywords.json.
JOBHIVE_SOURCES = [
    {"name": "jobhive", "collector": "jobhive"},
]

# NUworks (Northeastern Symplicity): authed JSON API, session in the shared
# `sessions` table (cURL-paste recovery like Handshake). Runs on its OWN timer
# (run.py nuworks) at a randomized 45-60 min offset to keep the polling cadence
# low-volume and unpredictable -- it can't ride the fast poller's timer without
# either firing hourly-on-the-dot or blocking the other fast sources. The URL
# carries the major/school filter; the collector stamps role_type per listing
# (co-op -> intern).
NUWORKS_SOURCES = [
    {"name": "nuworks", "collector": "nuworks",
     "url": "https://northeastern-csm.symplicity.com/api/v2/jobs?targeted_academic_majors=0160&screen_school=0240&sort=%21postdate"},
]

# YC 'Work at a Startup' (workatastartup.com): authed, Algolia-backed search.
# Self-acquiring collector (page -> Algolia ids -> /companies/fetch), session in
# the shared `sessions` table. Own randomized timer (run.py ycstartup), like
# NUworks, to keep the multi-step footprint low and unpredictable.
YCSTARTUP_SOURCES = [
    {"name": "ycstartup", "collector": "ycstartup"},
]

# Built In's engineering/AI boards and Simplify's general new-grad list aren't
# software-scoped -- they return every entry-level/new-grad role (sales, nursing,
# mechanical/electrical eng, analysts). Gate them on the shared software-domain
# title filter (config_store.wanted) so only software roles pass. The SWE-specific
# repos (simplify-intern, vansh, speedyapply) are already scoped and pass untouched.
FILTERED_SOURCES = {"builtin-engineering", "builtin-aiml", "simplify-newgrad"}

STATE_FILE = Path(__file__).with_name("state.json")
JOBHIVE_STATE_FILE = Path(__file__).with_name("state-jobhive.json")
NUWORKS_STATE_FILE = Path(__file__).with_name("state-nuworks.json")
YCSTARTUP_STATE_FILE = Path(__file__).with_name("state-ycstartup.json")


def main(sources, state_file, with_stats=False, header=None, color=None):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN not set")

    new = list(poll_all(sources, state_file, token))
    # Drop non-software roles from the un-scoped board feeds (Built In / general
    # new-grad list) before storing/notifying; the SWE-curated sources pass through.
    if any(l.source in FILTERED_SOURCES for l in new):
        inc, exc = config_store.keywords()
        new = [l for l in new if l.source not in FILTERED_SOURCES
               or config_store.wanted(l.title, inc, exc)]
    # Tag the priority flag once so the store and the Discord summary share it.
    new = [dataclasses.replace(l, priority=is_priority(l)) for l in new]

    # One id for this run: every row saved below is stamped with it, and the
    # Discord link carries it, so clicking the digest highlights exactly this
    # scrape's roles on the dashboard. Compact UTC timestamp -> unique per run.
    batch_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # Always log to stdout (the cron log keeps the history); also push to Discord
    # if a webhook is configured. A notify failure must not lose the run.
    for listing in new:
        print(f"[{listing.source}] {listing.display()}")

    # Persist first (durable record), then notify. Each sink is failure-isolated
    # so one being down doesn't lose the run or block the other.
    sb_url, sb_key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if sb_url and sb_key:
        try:
            SupabaseStore(sb_url, sb_key).save(new, batch_id=batch_id)
        except Exception as e:
            print(f"supabase store failed: {e}", file=sys.stderr)

    # Discord summarizes INTERN roles only (new-grad is still scraped + stored to
    # the dashboard, just not announced here). jobright posts its own intern
    # digest separately (engine/jobright.py).
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if webhook:
        interns = [l for l in new if l.role_type == "intern"]
        try:
            # The jobhive scrape-health line only makes sense on the jobhive run.
            get_notifier("discord")(webhook).send(
                interns, stats=jobhive_stats if with_stats else None,
                header=header, color=color, path="/all", batch_id=batch_id)
        except Exception as e:
            print(f"discord notify failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    # Two independently-scheduled groups (separate timers + state files) so the
    # slow ~3,300-company jobhive ATS scrape can't delay -- or, on timeout,
    # discard -- the fast GitHub-repo / Built In poll:
    #   run.py           -> repo + Built In sources (fast, hourly)
    #   run.py jobhive   -> jobhive ATS scrape only (slow, its own 2h timer)
    #   run.py nuworks   -> NUworks authed API only (its own randomized timer)
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "jobhive":
        main(JOBHIVE_SOURCES, JOBHIVE_STATE_FILE, with_stats=True)
    elif arg == "nuworks":
        # NUworks is the highest-priority signal (Northeastern-exclusive co-ops),
        # so its digest goes out as a crimson embed with a banner title to stand
        # apart from every other source's plain-text message.
        main(NUWORKS_SOURCES, NUWORKS_STATE_FILE,
             header="🚨🎓 NUWORKS — TOP-PRIORITY CO-OPS 🎓🚨",
             color=0xE11D48)
    elif arg == "ycstartup":
        # YC startups: its own YC-orange embed so it stands apart from NUworks
        # (crimson) and the plain-text sources.
        main(YCSTARTUP_SOURCES, YCSTARTUP_STATE_FILE,
             header="🟧 YC STARTUPS — new intern roles 🟧",
             color=0xFB651E)
    else:
        main(SOURCES, STATE_FILE)
