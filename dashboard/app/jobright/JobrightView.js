'use client';

import { useCallback, useEffect, useState } from 'react';
import { supabase } from '../../lib/supabase';

// Shared jobright view, reused by the /jobright route and the "Jobright Interns"
// tab on the Jobs page. jobright has its own table and its own H1B column, so it
// renders separately rather than merging into the main jobs table.
const SINCE = [
  { label: 'Last 24h', hours: 24 },
  { label: 'Last 7 days', hours: 168 },
  { label: 'Last 30 days', hours: 720 },
  { label: 'All time', hours: null },
];

const TWO_HOURS = 2 * 3600 * 1000;
// Posted within the last 2h -> show a NEW badge.
function isNew(job) {
  return job.posted_at && Date.now() - new Date(job.posted_at).getTime() < TWO_HOURS;
}

export default function JobrightView() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sinceHours, setSinceHours] = useState(168);
  const [hideApplied, setHideApplied] = useState(true);
  const [hideUnsure, setHideUnsure] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    let q = supabase
      .from('jobright_jobs')
      .select('*')
      .order('first_seen', { ascending: false })
      .limit(2000);
    if (sinceHours) {
      const since = new Date(Date.now() - sinceHours * 3600 * 1000).toISOString();
      q = q.gte('first_seen', since);
    }
    if (hideUnsure) q = q.eq('h1b_sponsored', 'Yes');
    const { data, error } = await q;
    if (error) setError(error.message);
    setJobs(data || []);
    setLoading(false);
  }, [sinceHours, hideUnsure]);

  useEffect(() => {
    load();
  }, [load]);

  async function toggle(job, field) {
    const value = !job[field];
    setJobs((js) => js.map((j) => (j.id === job.id ? { ...j, [field]: value } : j)));
    const { error } = await supabase.from('jobright_jobs').update({ [field]: value }).eq('id', job.id);
    if (error) {
      setError(error.message);
      load();
    }
  }

  async function remove(job) {
    if (!window.confirm(`Delete "${job.title}" at ${job.company}? This can't be undone.`)) return;
    setJobs((js) => js.filter((j) => j.id !== job.id));
    const { error } = await supabase.from('jobright_jobs').delete().eq('id', job.id);
    if (error) {
      setError(error.message);
      load();
    }
  }

  const visible = hideApplied ? jobs.filter((j) => !j.applied) : jobs;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-4">
        <label className="text-sm">
          Seen within{' '}
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
          <input type="checkbox" checked={hideUnsure} onChange={(e) => setHideUnsure(e.target.checked)} />
          H1B = Yes only
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
              <th className="px-3 py-2">H1B</th>
              <th className="px-3 py-2">Work</th>
              <th className="px-3 py-2">Posted</th>
              <th className="px-3 py-2">Apply</th>
              <th className="px-3 py-2 text-center">Applied</th>
              <th className="px-3 py-2 text-center">Referral</th>
              <th className="px-3 py-2 w-8"></th>
            </tr>
          </thead>
          <tbody>
            {visible.map((j) => (
              <tr key={j.id} className={`border-b last:border-0 ${j.h1b_sponsored === 'Yes' ? 'bg-green-50' : ''}`}>
                <td className="px-3 py-2 font-medium">{j.company}</td>
                <td className="px-3 py-2">
                  {j.title}
                  {isNew(j) && <span className="ml-2 rounded bg-green-100 px-1.5 py-0.5 text-xs font-medium text-green-700">NEW</span>}
                </td>
                <td className="px-3 py-2 text-gray-600">{j.location || '—'}</td>
                <td className="px-3 py-2 whitespace-nowrap text-gray-600">{j.salary || '—'}</td>
                <td className="px-3 py-2 whitespace-nowrap">
                  <span className={j.h1b_sponsored === 'Yes' ? 'text-green-700' : 'text-gray-500'}>
                    {j.h1b_sponsored || '—'}
                  </span>
                </td>
                <td className="px-3 py-2 text-gray-600">{j.work_model || '—'}</td>
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
            {!loading && visible.length === 0 && (
              <tr><td colSpan={11} className="px-3 py-6 text-center text-gray-500">No jobright jobs match these filters.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
