"""Discord provider: posts new listings to a channel via an incoming webhook.

A webhook needs no bot or OAuth -- create one in the channel settings and the
URL is the only secret. Messages are capped at 2000 characters, so listings are
packed into as few messages as fit under that limit.
"""

import requests

from notifiers.base import register

MAX_CHARS = 2000


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


@register("discord")
class DiscordNotifier:
    def __init__(self, webhook_url):
        self.webhook_url = webhook_url

    def send(self, listings):
        if not listings:
            return
        lines = [f"[{l.source}] {l.display()}" for l in listings]
        for content in _batch(lines, MAX_CHARS):
            resp = requests.post(self.webhook_url, json={"content": content}, timeout=30)
            resp.raise_for_status()
