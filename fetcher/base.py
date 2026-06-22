"""Fetcher backends: perform the actual network fetch for a source.

A backend is registered under a name and selected per-source via the optional
"fetcher" key in SOURCES (default "requests"). Each backend turns a URL + request
headers into a normalized Response, so the engine and parsers never depend on a
specific HTTP library -- a headless-browser backend can be swapped in later
without touching either. Cross-cutting transport settings (proxies, anti-bot,
timeout) live in config.py and apply to every backend.
"""

import json
from dataclasses import dataclass, field
from typing import Mapping, Protocol


@dataclass(frozen=True)
class Response:
    """The normalized shape every backend returns; mirrors the bits of an HTTP
    response the engine and parsers actually use."""
    status_code: int
    text: str
    headers: Mapping = field(default_factory=dict)

    def json(self):
        return json.loads(self.text)


class Fetcher(Protocol):
    def get(self, url, headers=None) -> Response:
        """Fetch url, return a Response. Raise on a non-2xx/304 status."""
        ...


_BACKENDS = {}


def register(name):
    def deco(fetcher):
        _BACKENDS[name] = fetcher
        return fetcher
    return deco


def get_fetcher(name):
    try:
        return _BACKENDS[name]
    except KeyError:
        raise KeyError(f"no fetcher registered as {name!r}; have {sorted(_BACKENDS)}")
