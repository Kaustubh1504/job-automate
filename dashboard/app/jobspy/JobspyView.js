'use client';

import { Fragment, useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useSearchParams } from 'next/navigation';
import { supabase } from '../../lib/supabase';
import { groupByDay, formatDay, effectiveTs } from '../../lib/batches';

// JobSpy keyword-search results (LinkedIn/Indeed/ZipRecruiter/Google). Own table,
// rendered as the "JobSpy" tab on the Jobs page -- separate from the main jobs
// table because these are broad keyword matches, not company-targeted scrapes.
const SINCE = [
  { label: 'Last 24h', hours: 24 },
  { label: 'Last 7 days', hours: 168 },
  { label: 'Last 30 days', hours: 720 },
  { label: 'All time', hours: null },
];

const TABS = [
  { key: 'all', label: 'All' },
  { key: 'intern', label: 'Intern' },
  { key: 'newgrad', label: 'New Grad' },
  { key: 'other', label: 'Other' },
];

// Same buckets as the main Jobs page. JobSpy keyword searches return noisy
// titles, so classify by the actual title (not the stored role_type) -- that's
// what surfaces mismatches into "Other".
const INTERN_RE = /\bintern(ship)?\b/i;
const NEWGRAD_RE = /\b(new\s?grad(uate)?|early\s?career|entry[-\s]?level|university\s?grad(uate)?|associate engineer)\b/i;
function roleOf(job) {
  const t = job.title || '';
  if (INTERN_RE.test(t)) return 'intern';
  if (NEWGRAD_RE.test(t)) return 'newgrad';
  return 'other';
}

const TWO_HOURS = 2 * 3600 * 1000;
// Posted within the last 2h -> show a NEW badge.
function isNew(job) {
  return job.posted_at && Date.now() - new Date(job.posted_at).getTime() < TWO_HOURS;
}

export default function JobspyView() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sinceHours, setSinceHours] = useState(24);
  const [hideApplied, setHideApplied] = useState(true);
  const [tab, setTab] = useState('all');
  // Discord deep-link: /jobspy?batch=<run id>. Rows carry batch_id, so we
  // highlight the ones this scrape found. Named batchId to avoid shadowing the
  // day-group `batch` in the render below.
  const batchId = useSearchParams().get('batch');
  const pathname = usePathname();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    let q = supabase
      .from('jobspy_jobs')
      .select('*')
      .not('dismissed', 'is', true) // hide soft-deleted rows (false or null shown)
      .order('first_seen', { ascending: false })
      .limit(2000);
    if (sinceHours) {
      const since = new Date(Date.now() - sinceHours * 3600 * 1000).toISOString();
      // posted within the window; fall back to first_seen when posted_at is null
      q = q.or(`posted_at.gte.${since},and(posted_at.is.null,first_seen.gte.${since})`);
    }
    const { data, error } = await q;
    if (error) setError(error.message);
    setJobs(data || []);
    setLoading(false);
  }, [sinceHours]);

  useEffect(() => {
    load();
  }, [load]);

  async function toggle(job, field) {
    const value = !job[field];
    setJobs((js) => js.map((j) => (j.id === job.id ? { ...j, [field]: value } : j)));
    const { error } = await supabase.from('jobspy_jobs').update({ [field]: value }).eq('id', job.id);
    if (error) {
      setError(error.message);
      load();
    }
  }

  // Soft-delete: mark dismissed so the next scrape (which re-upserts everything)
  // can't resurrect it. Upserts leave `dismissed` untouched.
  async function remove(job) {
    if (!window.confirm(`Remove "${job.title}" at ${job.company}? It won't come back.`)) return;
    setJobs((js) => js.filter((j) => j.id !== job.id));
    const { error } = await supabase.from('jobspy_jobs').update({ dismissed: true }).eq('id', job.id);
    if (error) {
      setError(error.message);
      load();
    }
  }

  // Counts per tab (over the loaded set, before the applied filter).
  const counts = jobs.reduce(
    (acc, j) => {
      acc.all += 1;
      acc[roleOf(j)] += 1;
      return acc;
    },
    { all: 0, intern: 0, newgrad: 0, other: 0 }
  );

  let visible = tab === 'all' ? jobs : jobs.filter((j) => roleOf(j) === tab);
  if (hideApplied) visible = visible.filter((j) => !j.applied);
  const hotCount = batchId ? visible.filter((j) => j.batch_id === batchId).length : 0;

  return (
    <div>
      {batchId && (
        <div className="mb-3 flex items-center gap-3 rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          <span>
            ✨ Highlighting {hotCount} {hotCount === 1 ? 'role' : 'roles'} from this scrape
            {hotCount === 0 ? ' (none in the current window — try a wider "Posted within")' : ''}.
          </span>
          <Link href={pathname} className="ml-auto text-blue-600 hover:underline">Clear</Link>
        </div>
      )}
      <div className="mb-4 flex gap-1 border-b">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm ${
              tab === t.key
                ? 'border-blue-600 font-medium text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-800'
            }`}
          >
            {t.label}
            <span className="text-gray-400"> ({counts[t.key]})</span>
          </button>
        ))}
      </div>

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
          {loading ? 'Loading…' : `${visible.length} shown`}
        </span>
      </div>

      {error && <p className="mb-3 rounded bg-red-50 p-2 text-sm text-red-700">{error}</p>}

      <div className="overflow-x-auto rounded border bg-white">
        <table className="w-full text-sm">
          <thead className="border-b bg-gray-50 text-left text-gray-600">
            <tr>
              <th className="px-3 py-2">Company</th>
              <th className="px-3 py-2">Title</th>
              <th className="px-3 py-2">Location</th>
              <th className="px-3 py-2">Salary</th>
              <th className="px-3 py-2">Source</th>
              <th className="px-3 py-2">Type</th>
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
                  <td colSpan={11} className="border-y px-3 py-1.5 text-xs font-semibold text-gray-600">
                    📅 {formatDay(batch.ts)} · {batch.rows.length} {batch.rows.length === 1 ? 'job' : 'jobs'}
                  </td>
                </tr>
                {batch.rows.map((j) => (
              <tr key={j.id} className={`border-b last:border-0 ${batchId && j.batch_id === batchId ? 'bg-amber-100 ring-1 ring-inset ring-amber-300' : ''}`}>
                <td className="px-3 py-2 font-medium">{j.company}</td>
                <td className="px-3 py-2">
                  {j.title}
                  {isNew(j) && <span className="ml-2 rounded bg-green-100 px-1.5 py-0.5 text-xs font-medium text-green-700">NEW</span>}
                </td>
                <td className="px-3 py-2 text-gray-600">{j.location || '—'}</td>
                <td className="px-3 py-2 whitespace-nowrap text-gray-600">{j.salary || '—'}</td>
                <td className="px-3 py-2 text-gray-500">{j.site || '—'}</td>
                <td className="px-3 py-2 text-gray-600">{j.job_type || '—'}</td>
                <td className="px-3 py-2 whitespace-nowrap text-gray-500">
                  {j.posted_at ? new Date(j.posted_at).toLocaleDateString() : '—'}
                </td>
                <td className="px-3 py-2">
                  {j.apply_url ? (
                    <a href={j.apply_url} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline">
                      open
                    </a>
                  ) : '—'}
                </td>
                <td className="px-3 py-2 text-center">
                  <input type="checkbox" checked={!!j.applied} onChange={() => toggle(j, 'applied')} />
                </td>
                <td className="px-3 py-2 text-center">
                  <input type="checkbox" checked={!!j.referred} onChange={() => toggle(j, 'referred')} />
                </td>
                <td className="px-3 py-2 text-center">
                  <button onClick={() => remove(j)} title="Delete from table" className="text-gray-400 hover:text-red-600">✕</button>
                </td>
              </tr>
                ))}
              </Fragment>
            ))}
            {!loading && visible.length === 0 && (
              <tr><td colSpan={11} className="px-3 py-6 text-center text-gray-500">No JobSpy jobs match these filters.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
