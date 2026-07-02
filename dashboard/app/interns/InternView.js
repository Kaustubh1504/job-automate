'use client';

import { Fragment, useCallback, useEffect, useState } from 'react';
import { supabase } from '../../lib/supabase';
import { groupByDay, formatDay, effectiveTs } from '../../lib/batches';

// Centralised intern view: pulls intern roles from every job-board table, merges
// them into one feed, dedupes across boards, and groups by posting day. This is
// the default landing tab.
const SINCE = [
  { label: 'Last 24h', hours: 24 },
  { label: 'Last 7 days', hours: 168 },
  { label: 'Last 30 days', hours: 720 },
  { label: 'All time', hours: null },
];

// Each board's table + how to label its "Board" column. The main `jobs` table
// aggregates many scrapers, so it reports its own per-row source.
const BOARDS = [
  { table: 'jobs', board: (r) => r.source || 'jobs' },
  { table: 'jobright_jobs', board: () => 'Jobright' },
  { table: 'jobspy_jobs', board: (r) => r.site || 'JobSpy' },
  { table: 'wellfound_jobs', board: () => 'Wellfound' },
];

const INTERN_RE = /\bintern(ship)?\b/i;
function isIntern(r) {
  return r.role_type === 'intern'
    || INTERN_RE.test(r.title || '')
    || (r.source || '').toLowerCase().includes('intern');
}

const TWO_HOURS = 2 * 3600 * 1000;
function isNew(row) {
  return row.posted_at && Date.now() - new Date(row.posted_at).getTime() < TWO_HOURS;
}

const tsNum = (r) => {
  const t = effectiveTs(r);
  return t ? Date.parse(t) : 0;
};

// `titleIncludes` (optional) further narrows to intern titles containing that
// substring -- used by the /2027 route to show only 2027 internships.
export default function InternView({ titleIncludes } = {}) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sinceHours, setSinceHours] = useState(24);
  const [hideApplied, setHideApplied] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    const since = sinceHours ? new Date(Date.now() - sinceHours * 3600 * 1000).toISOString() : null;

    // Config title filter (same keywords table config_store uses). Applied to
    // JobSpy's loose keyword-search results so unrelated titles (nurse, sales,
    // etc.) don't surface here as interns. Empty/unreadable -> no filtering.
    const { data: kw } = await supabase.from('keywords').select('term,kind');
    const inc = (kw || []).filter((k) => k.kind === 'include').map((k) => k.term.toLowerCase());
    const exc = (kw || []).filter((k) => k.kind === 'exclude').map((k) => k.term.toLowerCase());
    const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const titleOk = (title) => {
      const t = (title || '').toLowerCase();
      if (exc.some((x) => new RegExp(`\\b${esc(x)}\\b`).test(t.replace(/_/g, ' ')))) return false; // exclude wins
      return inc.length === 0 || inc.some((i) => new RegExp(`\\b${esc(i)}`).test(t));               // include at word-start
    };

    const results = await Promise.all(
      BOARDS.map(async (b) => {
        let q = supabase.from(b.table).select('*').not('dismissed', 'is', true).limit(1000);
        if (since) {
          q = q.or(`posted_at.gte.${since},and(posted_at.is.null,first_seen.gte.${since})`);
        }
        const { data, error } = await q;
        if (error) return { err: `${b.table}: ${error.message}` };
        const norm = (data || []).filter(isIntern).map((r) => ({
          key: `${b.table}:${r.id}`,
          table: b.table,
          id: r.id,
          company: r.company,
          title: r.title,
          location: r.location,
          salary: r.salary,
          apply_url: r.apply_url,
          posted_at: r.posted_at,
          first_seen: r.first_seen,
          board: b.board(r),
          applied: r.applied,
          referred: r.referred,
        }));
        return { rows: norm };
      })
    );

    const errs = results.filter((r) => r.err).map((r) => r.err);
    setError(errs.length ? errs.join(' · ') : null);

    // newest first, then dedupe the same role across boards (company + title).
    // JobSpy rows must also pass the config title filter (its search is loose).
    const needle = (titleIncludes || '').toLowerCase();
    const merged = results
      .flatMap((r) => r.rows || [])
      .filter((r) => r.table !== 'jobspy_jobs' || titleOk(r.title))
      .filter((r) => !needle || (r.title || '').toLowerCase().includes(needle))
      .sort((a, b) => tsNum(b) - tsNum(a));
    const seen = new Set();
    const deduped = [];
    for (const r of merged) {
      const k = `${(r.company || '').toLowerCase().trim()}|${(r.title || '').toLowerCase().trim()}`;
      if (seen.has(k)) continue;
      seen.add(k);
      deduped.push(r);
    }
    setRows(deduped);
    setLoading(false);
  }, [sinceHours, titleIncludes]);

  useEffect(() => {
    load();
  }, [load]);

  async function toggle(row, field) {
    const value = !row[field];
    setRows((rs) => rs.map((r) => (r.key === row.key ? { ...r, [field]: value } : r)));
    const { error } = await supabase.from(row.table).update({ [field]: value }).eq('id', row.id);
    if (error) {
      setError(error.message);
      load();
    }
  }

  async function remove(row) {
    setRows((rs) => rs.filter((r) => r.key !== row.key));
    const { error } = await supabase.from(row.table).update({ dismissed: true }).eq('id', row.id);
    if (error) {
      setError(error.message);
      load();
    }
  }

  const visible = hideApplied ? rows.filter((r) => !r.applied) : rows;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-4">
        <label className="text-sm">
          Posted within{' '}
          <select
            className="rounded border px-2 py-1"
            value={sinceHours ?? 'all'}
            onChange={(e) => setSinceHours(e.target.value === 'all' ? null : Number(e.target.value))}
          >
            {SINCE.map((o) => (
              <option key={o.label} value={o.hours ?? 'all'}>{o.label}</option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1 text-sm">
          <input type="checkbox" checked={hideApplied} onChange={(e) => setHideApplied(e.target.checked)} />
          Hide applied
        </label>
        <button onClick={load} className="rounded border bg-white px-3 py-1 text-sm hover:bg-gray-100">
          Refresh
        </button>
        <span className="ml-auto text-sm text-gray-500">
          {loading ? 'Loading…' : `${visible.length} interns across all boards`}
        </span>
      </div>

      {error && <p className="mb-3 rounded bg-red-50 p-2 text-sm text-red-700">{error}</p>}

      <div className="overflow-x-auto rounded border bg-white">
        <table className="w-full text-sm">
          <thead className="border-b bg-gray-50 text-left text-gray-600">
            <tr>
              <th className="px-3 py-2">Board</th>
              <th className="px-3 py-2">Company</th>
              <th className="px-3 py-2">Title</th>
              <th className="px-3 py-2">Location</th>
              <th className="px-3 py-2">Salary</th>
              <th className="px-3 py-2">Posted</th>
              <th className="px-3 py-2">Apply</th>
              <th className="px-3 py-2 text-center">Applied</th>
              <th className="px-3 py-2 text-center">Referral</th>
              <th className="px-3 py-2 w-8"></th>
            </tr>
          </thead>
          <tbody>
            {groupByDay(visible, effectiveTs).map((batch, bi) => (
              <Fragment key={`day-${bi}`}>
                <tr className="bg-gray-100/70">
                  <td colSpan={10} className="border-y px-3 py-1.5 text-xs font-semibold text-gray-600">
                    📅 {formatDay(batch.ts)} · {batch.rows.length} {batch.rows.length === 1 ? 'intern' : 'interns'}
                  </td>
                </tr>
                {batch.rows.map((r) => (
                  <tr key={r.key} className="border-b last:border-0">
                    <td className="px-3 py-2">
                      <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600">{r.board}</span>
                    </td>
                    <td className="px-3 py-2 font-medium">{r.company}</td>
                    <td className="px-3 py-2">
                      {r.title}
                      {isNew(r) && <span className="ml-2 rounded bg-green-100 px-1.5 py-0.5 text-xs font-medium text-green-700">NEW</span>}
                    </td>
                    <td className="px-3 py-2 text-gray-600">{r.location || '—'}</td>
                    <td className="px-3 py-2 whitespace-nowrap text-gray-600">{r.salary || '—'}</td>
                    <td className="px-3 py-2 whitespace-nowrap text-gray-500">
                      {r.posted_at ? new Date(r.posted_at).toLocaleDateString() : '—'}
                    </td>
                    <td className="px-3 py-2">
                      {r.apply_url ? (
                        <a href={r.apply_url} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline">
                          open
                        </a>
                      ) : '—'}
                    </td>
                    <td className="px-3 py-2 text-center">
                      <input type="checkbox" checked={!!r.applied} onChange={() => toggle(r, 'applied')} />
                    </td>
                    <td className="px-3 py-2 text-center">
                      <input type="checkbox" checked={!!r.referred} onChange={() => toggle(r, 'referred')} />
                    </td>
                    <td className="px-3 py-2 text-center">
                      <button onClick={() => remove(r)} title="Delete from table" className="text-gray-400 hover:text-red-600">✕</button>
                    </td>
                  </tr>
                ))}
              </Fragment>
            ))}
            {!loading && visible.length === 0 && (
              <tr><td colSpan={10} className="px-3 py-6 text-center text-gray-500">No intern roles match these filters.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
