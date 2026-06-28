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
      <Sessions />
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

// Login-protected sources whose sessions the scrapers refresh from a pasted cURL.
const SESSION_SOURCES = ['handshake', 'ziprecruiter', 'glassdoor', 'nuworks', 'ycstartup'];

// Pull the cookie jar + host out of a pasted cURL / copy-as-fetch / raw cookie
// header. Works for ANY source: the host is read from the request URL, and it
// includes the httpOnly auth cookies (it reads the request the browser actually
// sent, which JS/the console can't).
function extractSession(text) {
  // Capture up to the *matching* closing quote (\1), so a cookie value that
  // contains the other quote type -- e.g. g_state={"i_l":0,...} inside a
  // single-quoted curl -b '...' -- isn't truncated at that inner quote.
  const cm =
    text.match(/-H\s*(['"])cookie:\s*([\s\S]*?)\1/i) || // curl  -H 'cookie: ...'
    text.match(/\s-b\s*(['"])([\s\S]*?)\1/) ||          // curl  -b '...'
    text.match(/"cookie"\s*:\s*"([\s\S]*?)"/i) ||       // fetch  "cookie":"..."
    text.match(/^\s*cookie:\s*(.+)$/im);                // raw header line
  const hm = text.match(/https?:\/\/([^/'"\s]+)/i);   // first URL -> host
  if (!cm || !hm) return null;
  const host = `https://${hm[1]}`;
  // The cookie string is the last capture group (the quoted-curl patterns add a
  // leading quote group; the fetch/raw patterns don't).
  const cookies = cm[cm.length - 1]
    .trim()
    .split('; ')
    .filter((p) => p.includes('='))
    .map((p) => {
      const i = p.indexOf('=');
      return { name: p.slice(0, i), value: p.slice(i + 1), url: host };
    });
  return cookies.length ? { host, cookies } : null;
}

// ---- Login-protected source sessions ---------------------------------------
function Sessions() {
  const [rows, setRows] = useState([]);
  const [source, setSource] = useState(SESSION_SOURCES[0]);
  const [text, setText] = useState('');
  const [msg, setMsg] = useState('');

  const load = useCallback(async () => {
    const { data } = await supabase.from('sessions').select('source,status,host,updated_at');
    setRows(data || []);
  }, []);
  useEffect(() => { load(); }, [load]);

  async function refresh() {
    const parsed = extractSession(text);
    if (!parsed) {
      setMsg('Could not parse — paste the full request via Network tab → Copy as cURL (the console can’t see httpOnly cookies).');
      return;
    }
    const { error } = await supabase.from('sessions').upsert(
      { source, host: parsed.host, cookies: parsed.cookies, status: 'active',
        updated_at: new Date().toISOString() },
      { onConflict: 'source' });
    setMsg(error ? `Error: ${error.message}`
      : `✓ ${source}: saved ${parsed.cookies.length} cookies from ${parsed.host}.`);
    if (!error) setText('');
    load();
  }

  const bySource = Object.fromEntries(rows.map((r) => [r.source, r]));
  const anyExpired = rows.some((r) => r.status === 'expired');

  return (
    <Section
      title="Sessions"
      hint="Login-protected sources (Handshake, ZipRecruiter, Glassdoor, …) the scrapers sign in to with a saved cookie jar. When one expires, log in to that site, then DevTools → Network → Copy as cURL on any request, pick the source below, and paste it.">
      {anyExpired && (
        <div className="mb-3 rounded bg-red-100 px-3 py-2 text-sm text-red-700">
          ⚠️ One or more sessions expired — refresh below.
        </div>
      )}
      <table className="mb-4 w-full text-sm">
        <tbody>
          {SESSION_SOURCES.map((s) => {
            const r = bySource[s];
            const st = r?.status ?? 'none';
            return (
              <tr key={s} className="border-b last:border-0">
                <td className="py-1 pr-2 w-40">{s}</td>
                <td className="py-1 pr-2">
                  <span className={`rounded px-2 py-0.5 text-xs ${st === 'active' ? 'bg-green-100 text-green-700' : st === 'expired' ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-500'}`}>{st}</span>
                </td>
                <td className="py-1 pr-2 text-xs text-gray-400">
                  {r?.updated_at ? new Date(r.updated_at).toLocaleString() : ''}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="flex flex-wrap items-center gap-2">
        <select className="rounded border px-2 py-1" value={source} onChange={(e) => setSource(e.target.value)}>
          {SESSION_SOURCES.map((s) => <option key={s}>{s}</option>)}
        </select>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={3}
          placeholder="Paste 'Copy as cURL' for the selected source…"
          className="min-w-[20rem] flex-1 rounded border px-2 py-1 font-mono text-xs" />
      </div>
      <div className="mt-2 flex items-center gap-3">
        <button onClick={refresh} className="rounded bg-blue-600 px-3 py-1 text-white hover:bg-blue-700">
          Refresh session
        </button>
        {msg && <span className="text-sm text-gray-600">{msg}</span>}
      </div>
    </Section>
  );
}

// ---- Target companies -------------------------------------------------------
function Targets() {
  const [rows, setRows] = useState([]);
  const [ats, setAts] = useState('greenhouse');
  const [slug, setSlug] = useState('');

  const load = useCallback(async () => {
    // PostgREST caps a select at 1000 rows, so page through with .range() --
    // there are >3000 targets and the unpaginated query silently truncated.
    const PAGE = 1000;
    const all = [];
    for (let from = 0; ; from += PAGE) {
      const { data, error } = await supabase
        .from('targets').select('*').order('ats').order('slug')
        .range(from, from + PAGE - 1);
      if (error || !data || data.length === 0) break;
      all.push(...data);
      if (data.length < PAGE) break;
    }
    setRows(all);
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
