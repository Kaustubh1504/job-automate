"""The default backend: a plain `requests` GET over a reused session.

Applies the shared config (default headers, proxies, timeout) to every request,
then merges in the per-request headers the engine passes (auth, conditional
If-None-Match). A 304 is returned to the caller as-is; 4xx/5xx raise.
"""

import requests

from fetcher import config
from fetcher.base import Response, register


class RequestsFetcher:
    def __init__(self):
        self._session = requests.Session()

    def get(self, url, headers=None):
        merged = {**config.DEFAULT_HEADERS, **(headers or {})}
        resp = self._session.get(
            url,
            headers=merged,
            proxies=config.PROXIES or None,
            timeout=config.TIMEOUT,
        )
        resp.raise_for_status()
        return Response(resp.status_code, resp.text, resp.headers)


# Registered as a singleton: transport config is global, so there's nothing
# per-source to construct.
register("requests")(RequestsFetcher())
