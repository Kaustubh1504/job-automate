"""Live per-company ATS scrape via jobhive, mapped into the shared Listing.

Unlike the GitHub-repo sources (one URL + ETag + parser), this hits each tracked
company's ATS directly through jobhive's per-ATS scrapers, so a posting shows up
as soon as the company publishes it -- no maintainer/PR lag. A company's ATS
returns *every* open role, so results are trimmed by a title keyword filter
(config/keywords.json). Companies are scraped concurrently; one that fails is
logged and skipped so the rest still report.

Company list and filter live at the project root:
    config/targets.json   -- {ats, slug} per company (see that file's comment)
    config/keywords.json  -- include/exclude title terms (optional)
"""

import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from jobhive.scrapers import get_scraper

import config_store
from collectors.base import register
from listing import Listing

MAX_WORKERS = 8
JITTER_RANGE = (1.0, 5.0)   # seconds; randomized pause before each company scrape
REQUEST_TIMEOUT = 120       # seconds; per-request timeout for every ATS scraper

# Scrape health from the most recent collect(), read by run.py for the Discord
# digest. Mutated in place so importers see the latest run's counts.
LAST_RUN_STATS = {"failed": 0, "total": 0}


def _load_targets():
    return config_store.targets()


def _load_filter():
    include, exclude = config_store.keywords()
    return [w.lower() for w in include], [w.lower() for w in exclude]


def _wanted(title, include, exclude):
    if config_store.excluded(title, exclude):   # exclude wins (e.g. "Senior ...", PhD)
        return False
    # include matches at a word start so short tokens like "ai"/"ml" catch real
    # roles ("AI Engineer", "AI/ML", "AIOps") without matching "retAIl"/"Mumbai",
    # while "intern" still covers "internship".
    t = title.lower()
    return not include or any(re.search(rf"\b{re.escape(i)}", t) for i in include)


def _role_type(title):
    t = title.lower()
    if "intern" in t:
        return "intern"
    if any(k in t for k in ("new grad", "new graduate", "early career", "university grad", "entry level")):
        return "newgrad"
    return ""


# Multiplier to annualize a pay rate given its period (≈2080 work hours / 260
# work days a year). USD only -- no FX, no network.
_PERIOD_TO_YEAR = {"HOUR": 2080, "DAY": 260, "WEEK": 52, "MONTH": 12, "YEAR": 1}


def _annual_usd(job):
    if job.salary_currency not in (None, "USD"):
        return None
    amount = job.salary_max or job.salary_min      # upper bound of the range when present
    factor = _PERIOD_TO_YEAR.get(job.salary_period or "")
    return amount * factor if amount and factor else None


def _to_listing(job):
    return Listing(
        key=f"{job.ats_type.value}:{job.ats_id}",
        company=job.company,
        title=job.title,
        locations=(job.location,) if job.location else (),
        url=str(job.url),
        live=True,                          # the ATS only returns currently-open roles
        role_type=_role_type(job.title),
        annual_salary=_annual_usd(job),
    )


def _scrape(target, include, exclude):
    # Randomized jitter so we don't hit every ATS in lockstep (politeness +
    # lighter bot-detection footprint). jobhive's scrapers already back off on
    # 429/Retry-After per request, so we only add the inter-company jitter.
    delay = random.uniform(*JITTER_RANGE)
    print(f"[jobhive] sleeping {delay:.1f}s before {target['ats']}:{target['slug']}", file=sys.stderr)
    time.sleep(delay)
    jobs = get_scraper(target["ats"], target["slug"], timeout=REQUEST_TIMEOUT).fetch()
    return [_to_listing(j) for j in jobs if _wanted(j.title, include, exclude)]


@register("jobhive")
def collect(src):
    include, exclude = _load_filter()
    targets = _load_targets()
    out = []
    failed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_scrape, t, include, exclude): t for t in targets}
        for fut in as_completed(futures):
            t = futures[fut]
            try:
                out.extend(fut.result())
            except Exception as e:
                failed += 1
                print(f"[jobhive] {t['ats']}:{t['slug']} failed: {type(e).__name__}: {e}",
                      file=sys.stderr)
    LAST_RUN_STATS.update(failed=failed, total=len(targets))
    return out
