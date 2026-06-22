// All persistence lives in chrome.storage because the MV3 service worker is
// ephemeral (no reliable module-scope state). Dedup is ONLY platform job-id ->
// seen set, per collector; cross-source dedup is the pipeline's job, not ours.

const SEEN_CAP = 5000; // bound storage; keep the most recent ids
export const DEFAULT_ENDPOINT = 'http://localhost:8787/listings';

export async function getEndpoint(): Promise<string> {
  const { endpoint } = await chrome.storage.local.get('endpoint');
  return endpoint || DEFAULT_ENDPOINT;
}

export async function setEndpoint(endpoint: string): Promise<void> {
  await chrome.storage.local.set({ endpoint });
}

export async function getSeen(name: string): Promise<Set<string>> {
  const key = `seen:${name}`;
  const r = await chrome.storage.local.get(key);
  return new Set<string>(r[key] ?? []);
}

export async function markSeen(name: string, ids: string[]): Promise<void> {
  const key = `seen:${name}`;
  const r = await chrome.storage.local.get(key);
  const merged = [...new Set([...(r[key] ?? []), ...ids])].slice(-SEEN_CAP);
  await chrome.storage.local.set({ [key]: merged });
}

export async function setLastRun(summary: unknown): Promise<void> {
  await chrome.storage.local.set({ lastRun: { at: new Date().toISOString(), summary } });
}
