"""Persist reported jobs to Supabase via the PostgREST API (no SDK dependency).

Each run's new listings are upserted into the `jobs` table, keyed by the
cross-source dedup id (canonical url, or the listing's own key), so the same role
from two sources collapses to one row and re-runs are idempotent. Network
failures raise; the caller wraps the call so a storage outage doesn't lose the
poll.

Writes:
    global_id, company, title, location, apply_url, source, priority, min_years_exp
    (+ llm_junior_ok / llm_reason on the new-rows save only -- see save())
`global_id` (NOT NULL, unique) holds the cross-source dedup id and is the upsert
conflict target; `id` is a DB-generated uuid (left to default). `priority` is the
deterministic referral tag from classify.is_priority. `min_years_exp` is the YoE bar read out of
jobhive's description (engine/yoe.py), null for sources that expose no JD. The
table's `description` / `ats_type` / `is_remote` columns aren't on the Listing
yet (only jobhive's raw Job exposes them) and are left null; `updated_at` is
DB-managed.

Env: SUPABASE_URL, SUPABASE_KEY (a key with insert rights on `jobs`).
"""

import sys

import requests

from canonical import canonicalize

# Columns added by deploy/*.sql. If one hasn't been applied yet, save() drops it
# and retries rather than losing the batch (see save()).
OPTIONAL_COLUMNS = ("min_years_exp", "llm_junior_ok", "llm_reason", "batch_id")


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

    def _row(self, l, batch_id, fit=False):
        row = {
            "global_id": canonicalize(l.url) or l.key,
            "company": l.company,
            "title": l.title,
            "location": ", ".join(l.locations) or None,
            "apply_url": l.url,
            "source": l.source,
            "priority": l.priority,
            # Always present (null when a source has no post date) so a bulk upsert
            # keeps uniform keys -- PostgREST rejects rows with differing key sets.
            "posted_at": l.posted_at,
            # Same rule: null for every source except jobhive, which is the only
            # one exposing a JD to read the number out of (see engine/yoe.py).
            "min_years_exp": l.min_years_exp,
        }
        if batch_id:
            row["batch_id"] = batch_id
        if fit:
            # Uniform across the batch (null where the model wasn't asked or
            # failed) -- PostgREST rejects rows with differing key sets.
            row["llm_junior_ok"] = l.llm_junior_ok
            row["llm_reason"] = l.llm_reason
        return row

    def save(self, listings, batch_id=None, fit=False):
        # batch_id stamps every row from one run so the dashboard can highlight
        # that scrape's roles (see run.py / notifiers.discord). Omitted -> the
        # column is left untouched, so this stays safe before the migration.
        #
        # fit=True sends the llm_* verdict columns. Only the NEW-rows save passes
        # it: the store_all pass re-upserts every open role with no verdict, and
        # merge-duplicates updates every column it is given -- sending the keys
        # there would wipe the verdicts earlier runs wrote.
        if not listings:
            return
        rows = [self._row(l, batch_id, fit) for l in listings]
        resp = self._post(rows)

        # PostgREST rejects the WHOLE batch if it names a column the table
        # doesn't have (PGRST204), so a migration that hasn't been applied yet
        # would lose the entire run -- for every source, not just the new
        # column's. Retry once without the optional columns and say so loudly.
        # It names only ONE offending column per response, so drop and retry
        # until it stops complaining (bounded by the number of optional columns).
        dropped = []
        for _ in range(len(OPTIONAL_COLUMNS)):
            if not (resp.status_code == 400 and "PGRST204" in resp.text):
                break
            missing = [c for c in OPTIONAL_COLUMNS
                       if f"'{c}'" in resp.text and c not in dropped]
            if not missing:
                break
            for row in rows:
                for column in missing:
                    row.pop(column, None)
            dropped.extend(missing)
            resp = self._post(rows)

        if dropped:
            print(f"[store] {', '.join(dropped)} missing from `jobs` -- saved without "
                  f"them. Apply deploy/*.sql to stop losing this data.", file=sys.stderr)
        resp.raise_for_status()

    def _post(self, rows):
        return requests.post(
            self.endpoint,
            params={"on_conflict": "global_id"},
            json=rows,
            headers=self.headers,
            timeout=30,
        )
