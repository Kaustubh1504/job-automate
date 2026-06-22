import { postListings } from './bridge';
import { getCollectors } from './registry';
import { getSeen, markSeen, setLastRun } from './storage';

// The whole run loop, fully provider-agnostic: for each registered collector,
// collect() -> dedup by job-id -> log found/new -> POST new -> remember ids.
// A collector that throws is logged and skipped; the rest still run.
export async function runPoll(): Promise<Record<string, unknown>> {
  const summary: Record<string, unknown> = {};
  for (const c of getCollectors()) {
    try {
      const found = await c.collect();
      const seen = await getSeen(c.name);
      const fresh = found.filter((l) => !seen.has(l.jobId));
      console.log(`[${c.name}] found ${found.length}, new ${fresh.length}`, fresh);
      await postListings(fresh);
      await markSeen(c.name, found.map((l) => l.jobId));
      summary[c.name] = { found: found.length, new: fresh.length };
    } catch (e) {
      console.error(`[${c.name}] collect failed:`, e);
      summary[c.name] = { error: String(e) };
    }
  }
  await setLastRun(summary);
  console.log('[poll] done', summary);
  return summary;
}
