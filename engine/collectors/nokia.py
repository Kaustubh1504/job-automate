"""Live Nokia ATS scrape (Oracle Recruiting Cloud), mapped into the shared Listing.

A single-company watch, not a domain-scoped feed: the user wants to see EVERY
open Nokia posting -- any team, any seniority -- to apply to directly, so
neither the software-domain include filter nor the seniority exclude list
(config/keywords.json, meant for the un-scoped board feeds) is applied here --
both would drop postings the user explicitly wants to see. Only the shared
US-location filter is applied, matching the rest of the pipeline's scope.

ATS + slug found via jobs.nokia.com's redirect to its Oracle Fusion Candidate
Experience site (siteNumber CX_1).
"""

from jobhive.scrapers import get_scraper

import us_location
from collectors.base import register
from collectors.jobhive import _role_type
from listing import Listing

ATS = "oracle"
SLUG = "https://fa-evmr-saasfaprod1.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1"
REQUEST_TIMEOUT = 120


def _to_listing(job):
    return Listing(
        key=f"{job.ats_type.value}:{job.ats_id}",
        company="Nokia",             # job.company reports the ATS hostname, not "Nokia"
        title=job.title,
        locations=(job.location,) if job.location else (),
        url=str(job.url),
        live=True,
        role_type=_role_type(job.title),
    )


@register("nokia")
def collect(src):
    jobs = get_scraper(ATS, SLUG, timeout=REQUEST_TIMEOUT).fetch()
    return [_to_listing(j) for j in jobs if us_location.is_us_location(j.location)]
