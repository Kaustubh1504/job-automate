"""Resolve a company display name -> (ats, slug) using jobhive's published
companies dataset, so an unmonitored offsite listing can suggest which scraper
to add it under.

The dataset (columns: ats,name,slug,url) is fetched once via jobhive's manifest,
cached to disk with a TTL, and indexed by canonical company name. Network/parse
failures degrade to "unresolved" (resolve -> None); they never crash the caller.
"""

import csv
import io
import time
from pathlib import Path

import httpx

from company_norm import canon_company

_MANIFEST_URL = "https://storage.stapply.ai/jobhive/v1/manifest.json"
_BASE = "https://storage.stapply.ai/jobhive/v1/"
_CACHE = Path(__file__).resolve().parent / ".cache" / "companies.csv"
_TTL = 7 * 24 * 3600  # refetch weekly

_index = None  # canon_name -> (ats, slug)


def _download_csv():
    manifest = httpx.get(_MANIFEST_URL, timeout=60, follow_redirects=True).json()
    url = manifest["companies"]["csv"]
    if not url.startswith("http"):
        url = _BASE + url
    return httpx.get(url, timeout=120, follow_redirects=True).text


def _csv_text():
    if _CACHE.exists() and time.time() - _CACHE.stat().st_mtime < _TTL:
        return _CACHE.read_text()
    text = _download_csv()
    _CACHE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE.write_text(text)
    return text


def _load_index():
    global _index
    if _index is not None:
        return _index
    _index = {}
    try:
        reader = csv.DictReader(io.StringIO(_csv_text()))
        for row in reader:
            key = canon_company(row["name"])
            if key and key not in _index:  # first ATS wins on duplicate names
                _index[key] = (row["ats"], row["slug"])
    except Exception as e:  # offline / schema change -> resolve becomes a no-op
        print(f"[resolver] companies dataset unavailable, resolution disabled: {e}")
    return _index


def resolve(name):
    """Company display name -> (ats, slug) on a supported ATS, or None."""
    return _load_index().get(canon_company(name))
