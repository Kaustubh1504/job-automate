"""Shared transport config for every fetcher backend and every job board.

This is the single place to change cross-cutting network behaviour -- proxies,
default headers / user-agent, timeouts, and any future anti-bot settings -- so a
change here applies uniformly to every source and to every backend (the requests
backend today, a headless-browser backend later).
"""

# Seconds to wait per request before giving up.
TIMEOUT = 30

# Routed through every backend. Empty dict = direct connection. To add proxies
# later, set e.g. {"http": "http://user:pass@host:port", "https": "http://..."}.
PROXIES = {}

# Sent on every request. A realistic User-Agent is the cheapest bot-detection
# countermeasure; add more shared headers here as needed.
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}
