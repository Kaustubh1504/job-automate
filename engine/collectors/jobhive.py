"""Live per-company ATS scrape via jobhive, mapped into the shared Listing.

Unlike the GitHub-repo sources (one URL + ETag + parser), this hits each tracked
company's ATS directly through jobhive's per-ATS scrapers, so a posting shows up
as soon as the company publishes it -- no maintainer/PR lag. A company's ATS
returns *every* open role; this collector applies only the exclude rule + a
US-location filter, and defers the software-domain decision (keyword include +
the LLM classifier for ambiguous titles) to run.py's FILTERED_SOURCES gate.
Companies are scraped concurrently; one that fails is logged and skipped so the
rest still report.

Company list and filter live at the project root:
    config/targets.json   -- {ats, slug} per company (see that file's comment)
    config/keywords.json  -- include/exclude title terms (optional)
"""

import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from jobhive.scrapers import get_scraper

import config_store
import us_location
from collectors.base import register
from listing import Listing
from llm_fit import MAX_JD_CHARS
from newgrad import MAX_YEARS_EXP
from sponsorship import blocks_sponsorship
from yoe import min_years

MAX_WORKERS = 16            # ~3,300 targets; higher concurrency keeps the run well under its timeout
JITTER_RANGE = (1.0, 5.0)   # seconds; randomized pause before each company scrape
REQUEST_TIMEOUT = 120       # seconds; per-request timeout for every ATS scraper

# Scrape health from the most recent collect(), read by run.py for the Discord
# digest. Mutated in place so importers see the latest run's counts.
LAST_RUN_STATS = {"failed": 0, "total": 0}


def _load_targets():
    return config_store.targets()


def _load_exclude():
    return [w.lower() for w in config_store.keywords()[1]]


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
    years = min_years(job.description)
    # An explicit refusal to sponsor settles it without a model call, the way
    # jobright drops an explicit H1B "No". Silence is not a refusal.
    no_sponsorship = blocks_sponsorship(job.description)
    # Only these reach the fit judge, so only these carry their JD in memory: a
    # posting stating more than the bar, an internship (bucketed by title, never
    # New Grad), or one that won't sponsor is not worth a call.
    candidate = ((years is None or years <= MAX_YEARS_EXP)
                 and not no_sponsorship
                 and "intern" not in job.title.lower())
    return Listing(
        key=f"{job.ats_type.value}:{job.ats_id}",
        company=job.company,
        title=job.title,
        locations=(job.location,) if job.location else (),
        url=str(job.url),
        live=True,                          # the ATS only returns currently-open roles
        role_type=_role_type(job.title),
        annual_salary=_annual_usd(job),
        # The JD text rides along in the fetch we already pay for; we keep the
        # extracted number, not the description (~5KB/row unstored).
        min_years_exp=years,
        # Truncated and candidates-only: the full set is ~40k listings a cycle,
        # and holding every description would cost ~200MB for nothing.
        description=(job.description or "")[:MAX_JD_CHARS] if candidate else None,
        # Decided here rather than by the model, so it survives a run with no
        # login and shows up in the dashboard with its reason.
        llm_junior_ok=False if no_sponsorship else None,
        llm_reason="No sponsorship: the posting rules it out" if no_sponsorship else None,
    )


def _scrape(target, exclude):
    # Randomized jitter so we don't hit every ATS in lockstep (politeness +
    # lighter bot-detection footprint). jobhive's scrapers already back off on
    # 429/Retry-After per request, so we only add the inter-company jitter.
    delay = random.uniform(*JITTER_RANGE)
    print(f"[jobhive] sleeping {delay:.1f}s before {target['ats']}:{target['slug']}", file=sys.stderr)
    time.sleep(delay)
    jobs = get_scraper(target["ats"], target["slug"], timeout=REQUEST_TIMEOUT).fetch()
    # Apply only the exclude rule + US-location filter here; the software-domain
    # decision (keyword include, then the LLM classifier for ambiguous titles) is
    # made centrally in run.py, since jobhive is in FILTERED_SOURCES. Deferring
    # lets ambiguous-but-software titles reach the classifier instead of being
    # dropped by the include keyword filter. Location filter stays lenient
    # (ambiguous/blank/remote and US-paired multi-location strings are kept).
    return [_to_listing(j) for j in jobs
            if not config_store.excluded(j.title, exclude) and us_location.is_us_location(j.location)]


@register("jobhive")
def collect(src):
    exclude = _load_exclude()
    targets = _load_targets()
    out = []
    failed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_scrape, t, exclude): t for t in targets}
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
