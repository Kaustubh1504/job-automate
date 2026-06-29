'use client';

import { Fragment, useCallback, useEffect, useState } from 'react';
import { supabase } from '../lib/supabase';
import { groupByDay, formatDay, effectiveTs } from '../lib/batches';
import JobrightView from './jobright/JobrightView';
import JobspyView from './jobspy/JobspyView';
import HandshakeView from './handshake/HandshakeView';
import WellfoundView from './wellfound/WellfoundView';
import InternView from './interns/InternView';

const SINCE = [
  { label: 'Last 24h', hours: 24 },
  { label: 'Last 7 days', hours: 168 },
  { label: 'Last 30 days', hours: 720 },
  { label: 'All time', hours: null },
];

const TABS = [
  { key: 'interns', label: 'All Interns' }, // consolidated across every board; rendered by InternView
  { key: 'all', label: 'All' },
  { key: 'jobright', label: 'Jobright' }, // separate table; rendered by JobrightView
  { key: 'jobspy', label: 'JobSpy' }, // separate table; rendered by JobspyView
  { key: 'handshake', label: 'Handshake' }, // separate table; rendered by HandshakeView
  { key: 'wellfound', label: 'Wellfound' }, // separate table; rendered by WellfoundView
  { key: 'newgrad', label: 'New Grad' },
];

const TWO_HOURS = 2 * 3600 * 1000;
// Posted within the last 2h -> show a NEW badge.
function isNew(job) {
  return job.posted_at && Date.now() - new Date(job.posted_at).getTime() < TWO_HOURS;
}

const INTERN_RE = /\bintern(ship)?\b/i;
const NEWGRAD_RE = /\b(new\s?grad(uate)?|early\s?career|entry[-\s]?level|university\s?grad(uate)?|associate engineer)\b/i;

// Bucket a job into intern / newgrad / other. The repo sources encode the role
// in their name (authoritative); jobhive/live only reveal it via the title.
function roleOf(job) {
  const src = (job.source || '').toLowerCase();
  if (src.includes('intern')) return 'intern';
  if (src.includes('newgrad')) return 'newgrad';
  const t = job.title || '';
  if (INTERN_RE.test(t)) return 'intern';
  if (NEWGRAD_RE.test(t)) return 'newgrad';
  return 'other';
}

export default function JobsPage() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sinceHours, setSinceHours] = useState(24);
  const [hideApplied, setHideApplied] = useState(true);
  const [priorityOnly, setPriorityOnly] = useState(false);
  const [tab, setTab] = useState('interns');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    let q = supabase
      .from('jobs')
      .select('*')
      .not('dismissed', 'is', true) // hide soft-deleted rows (false or null shown)
      .order('first_seen', { ascending: false })
      .limit(2000);
    if (sinceHours) {
      const since = new Date(Date.now() - sinceHours * 3600 * 1000).toISOString();
      // posted within the window; fall back to first_seen when posted_at is null
      q = q.or(`posted_at.gte.${since},and(posted_at.is.null,first_seen.gte.${since})`);
    }
    if (priorityOnly) q = q.eq('priority', true);
    const { data, error } = await q;
    if (error) setError(error.message);
    setJobs(data || []);
    setLoading(false);
  }, [sinceHours, priorityOnly]);

  useEffect(() => {
    load();
  }, [load]);

  // Optimistic toggle for the applied / referred ticks.
  async function toggle(job, field) {
    const value = !job[field];
    setJobs((js) => js.map((j) => (j.id === job.id ? { ...j, [field]: value } : j)));
    const { error } = await supabase.from('jobs').update({ [field]: value }).eq('id', job.id);
    if (error) {
      setError(error.message);
      load(); // re-sync on failure
    }
  }

  // Soft-delete: mark dismissed instead of removing the row, so a re-scrape
  // (jobright re-upserts everything; the poller relies on state.json) can't
  // resurrect it. Upserts don't touch `dismissed`, so it stays hidden for good.
  async function remove(job) {
    if (!window.confirm(`Remove "${job.title}" at ${job.company}? It won't come back.`)) return;
    setJobs((js) => js.filter((j) => j.id !== job.id));
    const { error } = await supabase.from('jobs').update({ dismissed: true }).eq('id', job.id);
    if (error) {
      setError(error.message);
      load(); // re-sync on failure (e.g. RLS blocked the update)
    }
  }

  // Available jobs = loaded set minus applied (when hiding applied). Tab counts
  // reflect this base, so a tab's count matches the rows actually shown, not the
  // total.
  const available = hideApplied ? jobs.filter((j) => !j.applied) : jobs;
  const counts = available.reduce(
    (acc, j) => {
      acc.all += 1;
      const r = roleOf(j);
      if (r === 'intern' || r === 'newgrad') acc[r] += 1;
      return acc;
    },
    { all: 0, intern: 0, newgrad: 0 }
  );

  const visible = tab === 'all' ? available : available.filter((j) => roleOf(j) === tab);

  return (
    <div>
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
            {counts[t.key] !== undefined && <span className="text-gray-400"> ({counts[t.key]})</span>}
          </button>
        ))}
      </div>

      {tab === 'interns' ? (
        <InternView />
      ) : tab === 'jobright' ? (
        <JobrightView />
      ) : tab === 'jobspy' ? (
        <JobspyView />
      ) : tab === 'handshake' ? (
        <HandshakeView />
      ) : tab === 'wellfound' ? (
        <WellfoundView />
      ) : (
        <>
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
        <label className="flex items-center gap-1 text-sm">
          <input type="checkbox" checked={priorityOnly} onChange={(e) => setPriorityOnly(e.target.checked)} />
          Priority only
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
              <th className="px-3 py-2 w-8"></th>
              <th className="px-3 py-2">Company</th>
              <th className="px-3 py-2">Title</th>
              <th className="px-3 py-2">Location</th>
              <th className="px-3 py-2">Source</th>
              <th className="px-3 py-2">Seen</th>
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
                    📅 {formatDay(batch.ts)} · {batch.rows.length} {batch.rows.length === 1 ? 'job' : 'jobs'}
                  </td>
                </tr>
                {batch.rows.map((j) => (
              <tr key={j.id} className={`border-b last:border-0 ${j.priority ? 'bg-amber-50' : ''}`}>
                <td className="px-3 py-2" title={j.priority ? 'Priority / referral target' : ''}>
                  {j.priority ? '⭐' : ''}
                </td>
                <td className="px-3 py-2 font-medium">{j.company}</td>
                <td className="px-3 py-2">
                  {j.title}
                  {isNew(j) && <span className="ml-2 rounded bg-green-100 px-1.5 py-0.5 text-xs font-medium text-green-700">NEW</span>}
                </td>
                <td className="px-3 py-2 text-gray-600">{j.location || '—'}</td>
                <td className="px-3 py-2 text-gray-500">{j.source}</td>
                <td className="px-3 py-2 whitespace-nowrap text-gray-500">
                  {j.first_seen ? new Date(j.first_seen).toLocaleDateString() : '—'}
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
              <tr><td colSpan={10} className="px-3 py-6 text-center text-gray-500">No jobs match these filters.</td></tr>
            )}
          </tbody>
        </table>
      </div>
        </>
      )}
    </div>
  );
}
