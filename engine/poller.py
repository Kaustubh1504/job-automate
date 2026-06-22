"""The engine: fetch + ETag + per-source state + diff, aggregated across sources.

For each configured source it does a token-authenticated conditional GET (ETag /
If-None-Match), parses the response with the factory-selected parser, stamps
provenance onto each Listing, and reports the listings that have newly gone live
since the previous poll. New listings from every source are aggregated into one
list. A source that fails is logged and skipped so one being down doesn't stop
the rest.
"""

import dataclasses
import json
import os
import sys

from fetcher.base import get_fetcher

from canonical import canonicalize
from collectors.base import get_collector
from registry import get_parser


def _load(path):
    # A truncated/corrupt state file (e.g. a write killed mid-flight) must not
    # take down all polling: degrade to an empty baseline instead of crashing.
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (ValueError, OSError) as e:
        print(f"state file unreadable ({e}); starting from empty state", file=sys.stderr)
        return {}


def _save(path, state):
    # Write to a temp file then atomically rename, so a crash mid-write leaves
    # the previous good state.json intact rather than a half-written one.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state))
    os.replace(tmp, path)


def _poll_one(src, token, src_state):
    """Poll one source; return (new_live_listings, updated_src_state).

    Two source kinds: a "collector" acquires its own list[Listing] (no URL/ETag);
    otherwise it's a URL source -- conditional GET + parser on the response.
    """
    if "collector" in src:
        listings = get_collector(src["collector"])(src)
        etag = None
    else:
        headers = {"Authorization": f"Bearer {token}"}
        if src_state.get("etag"):
            headers["If-None-Match"] = src_state["etag"]

        fetch = get_fetcher(src.get("fetcher", "requests"))
        resp = fetch.get(src["url"], headers=headers)
        if resp.status_code == 304:      # unchanged since last poll
            return [], src_state

        listings = get_parser(src["parser"])(resp)
        etag = resp.headers.get("ETag")

    # Stamp provenance. role_type from the source config wins (the repo sources);
    # when the config omits it, keep what the collector derived per listing.
    listings = [
        dataclasses.replace(l, source=src["name"], role_type=src.get("role_type", l.role_type))
        for l in listings
    ]

    first_run = "announced_ids" not in src_state
    announced = set(src_state.get("announced_ids", []))
    live = [l for l in listings if l.live]

    # First run only records a baseline so the existing backlog isn't reported
    # as new. After that, a live listing with an unseen key is new.
    new = [] if first_run else [l for l in live if l.key not in announced]

    announced.update(l.key for l in live)
    return new, {"etag": etag, "announced_ids": sorted(announced)}


def poll_all(sources, state_file, token):
    """Poll every source once. Returns a flat aggregated list of new Listings.

    sources:    list of {"name", "url", "parser", "role_type"(optional)}
    state_file: pathlib.Path to the shared per-source JSON state store
    token:      GitHub token (repos are public; this only raises rate limits)
    """
    state = _load(state_file)
    # Cross-source dedup: a role found via two sources shares a canonical url, so
    # report it once. Falls back to the listing's own key when the url isn't a
    # recognized ATS shape. Monotonic, like announced_ids -- only ever drops
    # duplicates from the output, never re-fires, so no re-baseline needed.
    seen = set(state.get("_seen", []))
    aggregated = []
    for src in sources:
        name = src["name"]
        try:
            new, state[name] = _poll_one(src, token, state.get(name, {}))
        except Exception as e:
            print(f"[{name}] poll failed: {e}", file=sys.stderr)
            continue
        for l in new:
            key = canonicalize(l.url) or l.key
            if key in seen:
                continue
            seen.add(key)
            aggregated.append(l)
    state["_seen"] = sorted(seen)
    _save(state_file, state)
    return aggregated
