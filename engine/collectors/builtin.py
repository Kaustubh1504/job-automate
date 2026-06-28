"""Built In job-board collector (paginating).

Built In runs one national board (builtin.com) plus regional mirrors. The national
board with country=USA centralizes every metro, so a single search URL covers the
whole US -- no need to enumerate regional boards. Each board+filter is a static
SOURCES entry (collector="builtin", url=...); there's no config file.

Unlike the GitHub-repo sources (one URL + ETag + parser), a Built In search spans
several pages, so this is a collector: it pages through ?page=N until a page
returns no new cards, parsing the server-rendered job cards (not JS-gated -- the
shared browser UA in fetcher/config.py is enough).

Job ids are global across Built In, so each listing is keyed on its id and
resolved to its canonical builtin.com/job/<slug>/<id> URL; ids are deduped across
pages.
"""

import random
import time
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from collectors.base import register
from fetcher.base import get_fetcher
from listing import Listing

HUB = "https://builtin.com"
MAX_PAGES = 25            # safety ceiling; real daysSinceUpdated result sets end far sooner
PAGE_PAUSE = (1.0, 3.0)   # human-like gap between page fetches (politeness / lighter footprint)


def _page_url(base, page):
    """base URL with its `page` query param replaced by `page` (handles a base
    that already carries one)."""
    parts = urlparse(base)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k != "page"]
    query.append(("page", str(page)))
    return urlunparse(parts._replace(query=urlencode(query)))


def _text(el):
    return el.get_text(strip=True) if el else ""


def _role_type(title):
    # The search URL filters to internship + entry-level, so a title is either an
    # internship or an entry-level full-time (new-grad) role.
    return "intern" if "intern" in title.lower() else "newgrad"


def _cards(html):
    soup = BeautifulSoup(html, "html.parser")
    for card in soup.select('[data-id="job-card"]'):
        link = card.select_one('a[href^="/job/"]')
        title = _text(card.select_one('[data-id="job-card-title"]'))
        company = _text(card.select_one('[data-id="company-title"]'))
        if not (link and title and company):
            continue
        href = link.get("href", "")
        # Location text sits beside the pin icon: <i.fa-location-dot> ... <span>City</span>
        loc_icon = card.select_one("i.fa-location-dot")
        location = ""
        if loc_icon and loc_icon.parent and loc_icon.parent.parent:
            location = loc_icon.parent.parent.get_text(" ", strip=True)
        yield Listing(
            key=href.rstrip("/").rsplit("/", 1)[-1],   # global Built In job id
            company=company,
            title=title,
            locations=(location,) if location else (),
            url=urljoin(HUB, href),
            live=True,                                  # search pages list only open roles
            role_type=_role_type(title),
        )


@register("builtin")
def collect(src):
    fetch = get_fetcher("requests")
    out = {}
    for page in range(1, MAX_PAGES + 1):
        if page > 1:                              # jitter between pages, not before the first
            time.sleep(random.uniform(*PAGE_PAUSE))
        resp = fetch.get(_page_url(src["url"], page))
        rows = list(_cards(resp.text))
        new = [l for l in rows if l.key not in out]
        for l in new:
            out[l.key] = l
        # Stop on an empty page, or one that added nothing new (a board that
        # ignores the page param just re-serves page 1).
        if not rows or not new:
            break
    return list(out.values())
