"""Discord provider: posts a per-company summary of new roles via a webhook.

A webhook needs no bot or OAuth -- create one in the channel settings and the
URL is the only secret. Rather than one line per job, this sends a digest: how
many new roles per company (priority companies starred first), then a link to
the dashboard to actually view/apply. Messages are capped at 2000 chars, so the
summary is packed into as few messages as fit.
"""

from collections import Counter

import requests

from notifiers.base import register

MAX_CHARS = 2000
DASHBOARD_URL = "https://job-automate.vercel.app"


def _dashboard_link(path="/interns", batch_id=None):
    """Link to this scrape's own dashboard page (`path`, e.g. /jobright, /all) --
    each source deep-links to its section rather than the consolidated All Interns
    view. With a batch_id it further deep-links to that run so the page highlights
    the roles it found."""
    url = f"{DASHBOARD_URL}{path}"
    return f"{url}?batch={batch_id}" if batch_id else url


def _batch(lines, limit):
    """Group lines into newline-joined chunks, each at most `limit` chars."""
    buf, size = [], 0
    for line in lines:
        line = line[:limit]                      # never let one line exceed the cap
        extra = len(line) + (1 if buf else 0)    # +1 for the joining newline
        if size + extra > limit:
            yield "\n".join(buf)
            buf, size = [], 0
            extra = len(line)
        buf.append(line)
        size += extra
    if buf:
        yield "\n".join(buf)


def _summary(listings, header=None, stats=None, path="/interns", batch_id=None):
    """Lines for a per-company digest: priority companies first, then by count.
    An optional `header` line labels the section (e.g. for a jobright digest).
    An optional `stats` dict ({failed, total}) appends a scrape-health line.
    `path` picks this scrape's dashboard page; `batch_id` deep-links to this run."""
    counts = Counter(l.company for l in listings)
    priority = {l.company for l in listings if getattr(l, "priority", False)}
    total = len(listings)
    # priority companies first, then most roles first, then alphabetical
    order = sorted(counts, key=lambda c: (c not in priority, -counts[c], c.lower()))

    roles = "role" if total == 1 else "roles"
    cos = "company" if len(counts) == 1 else "companies"
    count_line = f"**{total} new {roles}** across {len(counts)} {cos}"
    lines = ([header, count_line] if header else [count_line]) + [""]
    for c in order:
        if c in priority:
            lines.append(f"⭐ **{c}** — {counts[c]} (priority)")
        else:
            lines.append(f"**{c}** — {counts[c]}")
    lines += ["", f"🔗 View & apply: {_dashboard_link(path, batch_id)}"]
    if stats and stats.get("total"):
        lines.append(f"📡 Scrape: {stats['failed']}/{stats['total']} targets failed")
    return lines


@register("discord")
class DiscordNotifier:
    def __init__(self, webhook_url):
        self.webhook_url = webhook_url

    def send(self, listings, header=None, stats=None, color=None, path="/interns", batch_id=None):
        if not listings:
            return
        # A `color` turns the digest into a colored embed (a card with a side-bar
        # + title) so a high-priority source stands out from the plain-text ones.
        # The digest is small enough to fit one embed (4096-char description cap).
        if color is not None:
            body = "\n".join(_summary(listings, None, stats, path, batch_id))[:4096]
            embed = {"description": body, "color": color}
            if header:
                embed["title"] = header          # title is inherently bold; pass plain text
            resp = requests.post(self.webhook_url, json={"embeds": [embed]}, timeout=30)
            resp.raise_for_status()
            return
        for content in _batch(_summary(listings, header, stats, path, batch_id), MAX_CHARS):
            resp = requests.post(self.webhook_url, json={"content": content}, timeout=30)
            resp.raise_for_status()
