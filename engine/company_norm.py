"""Canonical company key for fuzzy matching -- case/punctuation/suffix-insensitive,
with a small alias map for parents/rebrands (Alphabet -> Google, Facebook -> Meta).

Used to decide whether two company strings refer to the same employer, e.g. an
incoming LinkedIn "Google LLC" vs a monitored "google" slug, or "Alphabet" vs a
jobhive companies-dataset row. Pure string work, no network.
"""

import re

# Legal/structural suffixes dropped as standalone tokens (anywhere in the name).
_SUFFIXES = {
    "the", "inc", "incorporated", "llc", "lp", "llp", "ltd", "limited",
    "corp", "corporation", "co", "company", "gmbh", "plc", "sa", "ag",
    "nv", "bv", "holdings", "group",
}

# Aliases map a normalized variant -> its normalized canonical form. Both sides
# are already in canon form (lowercased, suffix-stripped, alnum-only).
_ALIASES = {
    "alphabet": "google",
    "googledeepmind": "google",
    "facebook": "meta",
    "metaplatforms": "meta",
    "aws": "amazon",
    "amazonwebservices": "amazon",
}


def canon_company(name):
    """'Alphabet Inc.' / 'Google LLC' -> 'google'; '' for empty/suffix-only."""
    if not name:
        return ""
    cleaned = re.sub(r"[^a-z0-9\s]", " ", name.lower())
    tokens = [t for t in cleaned.split() if t and t not in _SUFFIXES]
    key = "".join(tokens)
    return _ALIASES.get(key, key)
