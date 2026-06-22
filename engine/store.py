"""Persist reported jobs to Supabase via the PostgREST API (no SDK dependency).

Each run's new listings are upserted into the `jobs` table, keyed by the
cross-source dedup id (canonical url, or the listing's own key), so the same role
from two sources collapses to one row and re-runs are idempotent. Network
failures raise; the caller wraps the call so a storage outage doesn't lose the
poll.

Writes:
    global_id, company, title, location, apply_url, source, priority
`global_id` (NOT NULL, unique) holds the cross-source dedup id and is the upsert
conflict target; `id` is a DB-generated uuid (left to default). `priority` is the
deterministic referral tag from classify.is_priority. The table's `description` /
`posted_at` / `ats_type` / `is_remote` columns aren't on the Listing yet (only
jobhive's raw Job exposes them) and are left null; `updated_at` is DB-managed.

Env: SUPABASE_URL, SUPABASE_KEY (a key with insert rights on `jobs`).
"""

import requests

from canonical import canonicalize
from classify import is_priority


class SupabaseStore:
    def __init__(self, url, key, table="jobs"):
        self.endpoint = f"{url.rstrip('/')}/rest/v1/{table}"
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            # Upsert on global_id; don't send the rows back.
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }

    def _row(self, l):
        return {
            "global_id": canonicalize(l.url) or l.key,
            "company": l.company,
            "title": l.title,
            "location": ", ".join(l.locations) or None,
            "apply_url": l.url,
            "source": l.source,
            "priority": is_priority(l),
        }

    def save(self, listings):
        if not listings:
            return
        resp = requests.post(
            self.endpoint,
            params={"on_conflict": "global_id"},
            json=[self._row(l) for l in listings],
            headers=self.headers,
            timeout=30,
        )
        resp.raise_for_status()
