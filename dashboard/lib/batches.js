// Effective date for a row: prefer the job's posted date, fall back to
// first_seen (when the posting date is missing). Used for sorting, the
// "posted within" filter, and the day dividers so everything agrees.
export function effectiveTs(row) {
  return row.posted_at || row.first_seen || null;
}

// Group rows into one batch per calendar day of their effective date, newest
// day first (rows sorted by effective date desc within each day).
export function groupByDay(rows, getTs = effectiveTs) {
  const withTs = rows
    .map((row) => {
      const raw = getTs(row);
      return { row, t: raw ? new Date(raw).getTime() : null };
    })
    .sort((a, b) => (b.t ?? -Infinity) - (a.t ?? -Infinity));

  const batches = [];
  let dayKey = null;
  for (const { row, t } of withTs) {
    const key = t != null ? new Date(t).toDateString() : 'unknown';
    if (!batches.length || key !== dayKey) {
      batches.push({ ts: t != null ? new Date(t).toISOString() : null, rows: [row] });
      dayKey = key;
    } else {
      batches[batches.length - 1].rows.push(row);
    }
  }
  return batches;
}

// "Jun 28, 2026" -- the day label for a divider.
export function formatDay(ts) {
  if (!ts) return 'Unknown date';
  return new Date(ts).toLocaleDateString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
  });
}
