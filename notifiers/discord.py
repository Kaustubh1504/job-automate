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
DASHBOARD_URL = "https://job-automate.vercel.app/"


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


def _summary(listings):
    """Lines for a per-company digest: priority companies first, then by count."""
    counts = Counter(l.company for l in listings)
    priority = {l.company for l in listings if getattr(l, "priority", False)}
    total = len(listings)
    # priority companies first, then most roles first, then alphabetical
    order = sorted(counts, key=lambda c: (c not in priority, -counts[c], c.lower()))

    roles = "role" if total == 1 else "roles"
    cos = "company" if len(counts) == 1 else "companies"
    lines = [f"**{total} new {roles}** across {len(counts)} {cos}", ""]
    for c in order:
        if c in priority:
            lines.append(f"⭐ **{c}** — {counts[c]} (priority)")
        else:
            lines.append(f"**{c}** — {counts[c]}")
    lines += ["", f"🔗 View & apply: {DASHBOARD_URL}"]
    return lines


@register("discord")
class DiscordNotifier:
    def __init__(self, webhook_url):
        self.webhook_url = webhook_url

    def send(self, listings):
        if not listings:
            return
        for content in _batch(_summary(listings), MAX_CHARS):
            resp = requests.post(self.webhook_url, json={"content": content}, timeout=30)
            resp.raise_for_status()
