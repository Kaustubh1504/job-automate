"""Deterministic priority/referral classification -- a cheap, no-LLM pass.

A listing is flagged priority when EITHER:
  - its annualized USD salary clears the threshold (hourly_threshold * 2080), OR
  - its company is in the allowlist (FAANG+/Quant and any other referral targets).

The OR is deliberate: a known-company listing with no salary data still flags.
Config (threshold + allowlist) lives in config/priority.json. Reach for an LLM
only as a last-resort gap-filler for "is this unknown company established?" --
that does not belong here.
"""

import json
import re
from pathlib import Path

_CONFIG = Path(__file__).resolve().parents[1] / "config" / "priority.json"


def _norm(name):
    """Case/punctuation-insensitive company key: 'Jane Street' -> 'janestreet'."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _load():
    cfg = json.loads(_CONFIG.read_text())
    annual_threshold = cfg.get("hourly_threshold", 0) * 2080
    allowlist = {_norm(c) for c in cfg.get("allowlist", [])}
    return annual_threshold, allowlist


_ANNUAL_THRESHOLD, _ALLOWLIST = _load()


def is_priority(listing):
    if listing.annual_salary is not None and listing.annual_salary >= _ANNUAL_THRESHOLD:
        return True
    return _norm(listing.company) in _ALLOWLIST
