"""Parser for SpeedyApply's markdown job tables.

SpeedyApply keeps no JSON data file in its repo, only rendered markdown tables
backed by a private database. We parse the tables directly and key each listing
on its apply URL. This is inherently more fragile than the JSON sources: if
SpeedyApply restructures its tables, this module needs updating -- but only this
module.

Rows are mapped by header name, not column position, because the column set
varies between sections (the "Other" section drops the Salary column) and the
company / posting cells may or may not contain HTML.
"""

import html
import re
from datetime import datetime, timedelta, timezone

from listing import Listing
from registry import register
from us_location import is_us_location

_HREF = re.compile(r'href="([^"]+)"')
_TAGS = re.compile(r"<[^>]+>")
# PhD-specific roles are out of scope. Matches "PhD", "Ph.D", "Ph. D", "PHD".
_PHD = re.compile(r"\bph\.?\s?d\b", re.I)

# SpeedyApply's "Age" column ("0d", "9d", "3w", "2mo") -> hours. We keep only
# postings under MAX_AGE_HOURS: applying as fast as possible + polling hourly
# means a role (shown as "0d" for its whole first day) is caught while fresh and
# deduped thereafter, so nothing is missed. Age is day-granular, so 24h keeps the
# "0d" rows only.
MAX_AGE_HOURS = 24
_AGE = re.compile(r"(\d+)\s*(mo|[hdwy])", re.I)
_AGE_HOURS = {"h": 1, "d": 24, "w": 168, "mo": 720, "y": 8760}


def _text(cell):
    return html.unescape(_TAGS.sub("", cell)).strip()


def _age_hours(cell):
    """Age cell -> hours, or None if absent/unrecognized. None fails open (the
    row is kept), so a table-format change can't silently empty the feed."""
    m = _AGE.search(cell.lower())
    return int(m.group(1)) * _AGE_HOURS[m.group(2)] if m else None


def _is_separator(cells):
    return bool(cells) and all(c and set(c) <= set("-:") for c in cells)


@register("speedyapply")
def parse(resp):
    listings = []
    headers = None
    for raw in resp.text.splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            headers = None                       # any non-row line ends the table
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if _is_separator(cells):
            continue
        lowered = [c.lower() for c in cells]
        if "company" in lowered and "position" in lowered:
            headers = lowered                    # header row for a new table
            continue
        if headers is None:
            continue
        row = dict(zip(headers, cells))
        company = _text(row.get("company", ""))
        title = _text(row.get("position", ""))
        location = _text(row.get("location", ""))
        m = _HREF.search(row.get("posting", ""))
        url = m.group(1) if m else ""
        if not (company and title):
            continue
        # Same repo-feed gate as the JSON sources: US-only, no PhD roles.
        if not is_us_location(location) or _PHD.search(title):
            continue
        # Recency gate: drop stale postings (the table retains roles for weeks).
        age_h = _age_hours(_text(row.get("age", "")))
        if age_h is not None and age_h >= MAX_AGE_HOURS:
            continue
        posted_at = (datetime.now(timezone.utc) - timedelta(hours=age_h)).isoformat() if age_h is not None else None
        listings.append(Listing(
            key=url or f"{company}|{title}|{location}",
            company=company,
            title=title,
            locations=(location,) if location else (),
            url=url,
            live=True,                           # only current listings are in the tables
            posted_at=posted_at,
        ))
    return listings
