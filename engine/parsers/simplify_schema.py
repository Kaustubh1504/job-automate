"""Parser for the Pitt CSC / Simplify listings.json schema.

Shared by Simplify and vansh; their internship and new-grad repos all use this
identical schema, so each is just a source-config entry pointing here.
"""

import re
from datetime import datetime, timezone

from listing import Listing
from registry import register
from us_location import is_us_location

# PhD-specific roles are out of scope. Matches "PhD", "Ph.D", "Ph. D", "PHD".
_PHD = re.compile(r"\bph\.?\s?d\b", re.I)

# Recency gate: drop postings older than MAX_AGE_HOURS by date_posted. Like the
# speedyapply feed, these repos retain roles for weeks; hourly polling catches a
# role while fresh and dedups thereafter, so nothing is missed. Missing/zero
# date_posted fails open (kept), so a feed that omits it isn't silently emptied.
MAX_AGE_HOURS = 24


def _iso(ts):
    """Unix seconds -> ISO 8601 UTC, or None. date_posted/date_updated are epochs."""
    if not ts:
        return None
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def _too_old(ts):
    if not ts:
        return False
    return (datetime.now(timezone.utc).timestamp() - ts) / 3600 >= MAX_AGE_HOURS


@register("simplify_schema")
def parse(resp):
    out = []
    for j in resp.json():
        locations = tuple(j.get("locations", []))
        # These GitHub-repo feeds aren't US/PhD-scoped upstream (unlike jobhive),
        # so gate every repo listing here: drop non-US locations and PhD roles.
        if not is_us_location(", ".join(locations)) or _PHD.search(j["title"] or ""):
            continue
        if _too_old(j.get("date_posted")):
            continue
        out.append(Listing(
            key=j["id"],
            company=j["company_name"],
            title=j["title"],
            locations=locations,
            url=j["url"],
            live=bool(j.get("active") and j.get("is_visible")),
            posted_at=_iso(j.get("date_posted")),
        ))
    return out
