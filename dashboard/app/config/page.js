'use client';

import { useCallback, useEffect, useState } from 'react';
import { supabase } from '../../lib/supabase';

const ATS = [
  'greenhouse', 'lever', 'ashby', 'smartrecruiters', 'workday', 'workable', 'rippling',
  'personio', 'gem', 'icims', 'jazzhr', 'breezy', 'teamtailor', 'pinpoint', 'bamboohr',
  'cornerstone', 'recruitee', 'eightfold', 'avature', 'phenom', 'oracle', 'successfactors',
  'taleo', 'mercor', 'amazon', 'apple', 'google', 'tiktok', 'uber', 'meta', 'tesla',
];

export default function ConfigPage() {
  return (
    <div className="space-y-10">
      <Targets />
      <Keywords />
      <Priority />
    </div>
  );
}

function Section({ title, hint, children }) {
  return (
    <section>
      <h2 className="text-lg font-semibold">{title}</h2>
      {hint && <p className="mb-3 text-sm text-gray-500">{hint}</p>}
      <div className="rounded border bg-white p-4">{children}</div>
    </section>
  );
}

// ---- Target companies -------------------------------------------------------
function Targets() {
  const [rows, setRows] = useState([]);
  const [ats, setAts] = useState('greenhouse');
  const [slug, setSlug] = useState('');

  const load = useCallback(async () => {
    const { data } = await supabase.from('targets').select('*').order('ats').order('slug');
    setRows(data || []);
  }, []);
  useEffect(() => { load(); }, [load]);

  async function add(e) {
    e.preventDefault();
    if (!slug.trim()) return;
    await supabase.from('targets').upsert({ ats, slug: slug.trim() }, { onConflict: 'ats,slug' });
    setSlug('');
    load();
  }
  async function toggleActive(r) {
    await supabase.from('targets').update({ active: !r.active }).eq('id', r.id);
    load();
  }
  async function remove(r) {
    await supabase.from('targets').delete().eq('id', r.id);
    load();
  }

  return (
    <Section title="Target companies" hint="Companies scraped live each cycle. For Workday, slug is the full careers URL; big-tech (amazon/apple/google/…) slug is ignored but required.">
      <form onSubmit={add} className="mb-4 flex flex-wrap gap-2">
        <select className="rounded border px-2 py-1" value={ats} onChange={(e) => setAts(e.target.value)}>
          {ATS.map((a) => <option key={a}>{a}</option>)}
        </select>
        <input className="min-w-[18rem] flex-1 rounded border px-2 py-1" placeholder="slug or Workday URL" value={slug} onChange={(e) => setSlug(e.target.value)} />
        <button className="rounded bg-blue-600 px-3 py-1 text-white hover:bg-blue-700">Add</button>
      </form>
      <div className="max-h-96 overflow-y-auto">
        <table className="w-full text-sm">
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b last:border-0">
                <td className="py-1 pr-2 text-gray-500 w-32">{r.ats}</td>
                <td className="py-1 pr-2 break-all">{r.slug}</td>
                <td className="py-1 pr-2 text-right">
                  <button onClick={() => toggleActive(r)} className={`mr-2 rounded px-2 py-0.5 text-xs ${r.active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                    {r.active ? 'active' : 'paused'}
                  </button>
                  <button onClick={() => remove(r)} className="text-red-600 hover:underline text-xs">delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-gray-400">{rows.length} companies</p>
    </Section>
  );
}

// ---- Keywords ---------------------------------------------------------------
function Keywords() {
  const [rows, setRows] = useState([]);
  const load = useCallback(async () => {
    const { data } = await supabase.from('keywords').select('*').order('term');
    setRows(data || []);
  }, []);
  useEffect(() => { load(); }, [load]);

  async function add(kind, term) {
    if (!term.trim()) return;
    await supabase.from('keywords').upsert({ term: term.trim(), kind }, { onConflict: 'term,kind' });
    load();
  }
  async function remove(r) {
    await supabase.from('keywords').delete().eq('id', r.id);
    load();
  }

  return (
    <Section title="Keywords" hint="Title filter for scraped roles. Keep a role if it matches any include term and no exclude term.">
      <div className="grid gap-6 md:grid-cols-2">
        <KeywordList label="Include" items={rows.filter((r) => r.kind === 'include')} onAdd={(t) => add('include', t)} onRemove={remove} />
        <KeywordList label="Exclude" items={rows.filter((r) => r.kind === 'exclude')} onAdd={(t) => add('exclude', t)} onRemove={remove} />
      </div>
    </Section>
  );
}

function KeywordList({ label, items, onAdd, onRemove }) {
  const [term, setTerm] = useState('');
  return (
    <div>
      <h3 className="mb-2 font-medium">{label}</h3>
      <form onSubmit={(e) => { e.preventDefault(); onAdd(term); setTerm(''); }} className="mb-2 flex gap-2">
        <input className="flex-1 rounded border px-2 py-1" placeholder={`add ${label.toLowerCase()} term`} value={term} onChange={(e) => setTerm(e.target.value)} />
        <button className="rounded bg-blue-600 px-3 py-1 text-white hover:bg-blue-700">Add</button>
      </form>
      <div className="flex flex-wrap gap-2">
        {items.map((r) => (
          <span key={r.id} className="flex items-center gap-1 rounded bg-gray-100 px-2 py-0.5 text-sm">
            {r.term}
            <button onClick={() => onRemove(r)} className="text-gray-400 hover:text-red-600">×</button>
          </span>
        ))}
      </div>
    </div>
  );
}

// ---- Priority allowlist + threshold ----------------------------------------
function Priority() {
  const [rows, setRows] = useState([]);
  const [name, setName] = useState('');
  const [threshold, setThreshold] = useState('');

  const load = useCallback(async () => {
    const { data } = await supabase.from('priority_companies').select('*').order('name');
    setRows(data || []);
    const { data: s } = await supabase.from('settings').select('value').eq('key', 'hourly_threshold').maybeSingle();
    setThreshold(s?.value ?? '');
  }, []);
  useEffect(() => { load(); }, [load]);

  async function addCompany(e) {
    e.preventDefault();
    if (!name.trim()) return;
    await supabase.from('priority_companies').upsert({ name: name.trim() }, { onConflict: 'name' });
    setName('');
    load();
  }
  async function remove(r) {
    await supabase.from('priority_companies').delete().eq('id', r.id);
    load();
  }
  async function saveThreshold(e) {
    e.preventDefault();
    await supabase.from('settings').upsert({ key: 'hourly_threshold', value: String(threshold) }, { onConflict: 'key' });
  }

  return (
    <Section title="Priority" hint="A listing is flagged priority when its annualized salary ≥ threshold×2080, OR its company is in this allowlist.">
      <form onSubmit={saveThreshold} className="mb-4 flex items-center gap-2 text-sm">
        <label>Hourly threshold ($)</label>
        <input type="number" className="w-24 rounded border px-2 py-1" value={threshold} onChange={(e) => setThreshold(e.target.value)} />
        <button className="rounded border bg-white px-3 py-1 hover:bg-gray-100">Save</button>
      </form>
      <form onSubmit={addCompany} className="mb-3 flex gap-2">
        <input className="flex-1 rounded border px-2 py-1" placeholder="add company to allowlist" value={name} onChange={(e) => setName(e.target.value)} />
        <button className="rounded bg-blue-600 px-3 py-1 text-white hover:bg-blue-700">Add</button>
      </form>
      <div className="flex flex-wrap gap-2">
        {rows.map((r) => (
          <span key={r.id} className="flex items-center gap-1 rounded bg-amber-100 px-2 py-0.5 text-sm">
            {r.name}
            <button onClick={() => remove(r)} className="text-amber-500 hover:text-red-600">×</button>
          </span>
        ))}
      </div>
    </Section>
  );
}
