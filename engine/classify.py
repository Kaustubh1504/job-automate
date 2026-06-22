"""Deterministic priority/referral classification -- a cheap, no-LLM pass.

A listing is flagged priority when EITHER:
  - its annualized USD salary clears the threshold (hourly_threshold * 2080), OR
  - its company is in the allowlist (FAANG+/Quant and any other referral targets).

The OR is deliberate: a known-company listing with no salary data still flags.
Config (threshold + allowlist) comes from config_store (Supabase, JSON fallback)
and is loaded lazily and cached per process. Reach for an LLM only as a
last-resort gap-filler for "is this unknown company established?" -- not here.
"""

import re

import config_store


def _norm(name):
    """Case/punctuation-insensitive company key: 'Jane Street' -> 'janestreet'."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


_cache = None


def _config():
    global _cache
    if _cache is None:
        hourly, allowlist = config_store.priority()
        _cache = (hourly * 2080, {_norm(c) for c in allowlist})
    return _cache


def is_priority(listing):
    annual_threshold, allowlist = _config()
    if listing.annual_salary is not None and listing.annual_salary >= annual_threshold:
        return True
    return _norm(listing.company) in allowlist
