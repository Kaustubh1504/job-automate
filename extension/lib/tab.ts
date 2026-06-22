// Shared helper a tab-based collector uses: open the job-search URL in a
// BACKGROUND tab (reusing the logged-in session), run a self-contained scrape
// function in the page (DOM access), return its result, always close the tab.
// Never opens per-job pages. The worker doesn't know or care this happened.

const LOAD_TIMEOUT_MS = 120_000; // cap on waiting for the page shell to load (2 min)
const POLL_MS = 500;            // status poll interval (avoids onUpdated races)
const RENDER_WAIT_MS = 3_000;   // let the SPA paint before each scrape attempt
const SCRAPE_ATTEMPTS = 3;      // retry: SPAs fill the list after load fires

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

// Poll tab.status instead of listening for onUpdated — the event can fire before
// a listener attaches. On timeout we proceed (and scrape anyway) rather than fail.
async function waitForLoad(tabId: number): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < LOAD_TIMEOUT_MS) {
    const tab = await chrome.tabs.get(tabId).catch(() => null);
    if (!tab) return; // tab closed
    if (tab.status === 'complete') return;
    await delay(POLL_MS);
  }
  console.warn('[tab] load not confirmed before timeout; scraping anyway');
}

// scrapeFunc is serialized and injected, so it must be self-contained: no
// imports, no references to module/outer scope.
export async function collectViaTab<T>(url: string, scrapeFunc: () => T[]): Promise<T[]> {
  const tab = await chrome.tabs.create({ url, active: false });
  const tabId = tab.id!;
  try {
    await waitForLoad(tabId);
    let result: T[] = [];
    for (let attempt = 0; attempt < SCRAPE_ATTEMPTS; attempt++) {
      await delay(RENDER_WAIT_MS);
      const [{ result: r }] = await chrome.scripting.executeScript({ target: { tabId }, func: scrapeFunc });
      result = (r ?? []) as T[];
      if (result.length) break; // got cards — stop early
    }
    return result;
  } finally {
    try {
      await chrome.tabs.remove(tabId);
    } catch {
      /* tab already gone */
    }
  }
}
