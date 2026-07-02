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

from listing import Listing
from registry import register
from us_location import is_us_location

_HREF = re.compile(r'href="([^"]+)"')
_TAGS = re.compile(r"<[^>]+>")
# PhD-specific roles are out of scope. Matches "PhD", "Ph.D", "Ph. D", "PHD".
_PHD = re.compile(r"\bph\.?\s?d\b", re.I)


def _text(cell):
    return html.unescape(_TAGS.sub("", cell)).strip()


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
        listings.append(Listing(
            key=url or f"{company}|{title}|{location}",
            company=company,
            title=title,
            locations=(location,) if location else (),
            url=url,
            live=True,                           # only current listings are in the tables
        ))
    return listings
