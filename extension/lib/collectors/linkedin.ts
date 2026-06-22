import { register } from '../registry';
import { collectViaTab } from '../tab';
import type { Collector, NormalizedListing } from '../types';

const NAME = 'linkedin';
const HOST = 'www.linkedin.com';

// Logged-in jobs search. Edit these to taste — keywords, location, recency.
//   f_TPR=r86400 -> posted in the last 24h | sortBy=DD -> newest first
//   geoId=103644278 -> United States       | distance=0.0 -> exact location
const KEYWORDS = 'software or ai ml intern';
const GEO_ID = '103644278';
const PARAMS = `keywords=${encodeURIComponent(KEYWORDS)}&geoId=${GEO_ID}&distance=0.0&f_TPR=r86400&sortBy=DD`;

// LinkedIn paginates with `start` in steps of PAGE_SIZE. Build one page's URL.
// We target /jobs/search-results/ because the classic /jobs/search/ page now
// redirects to an error/the new UI for migrated accounts. The new UI's class
// names are obfuscated and rotate per deploy, so the scrape below anchors on the
// stable /jobs/view/ link (gives both id + url) rather than CSS classes.
const PAGE_SIZE = 25;        // results per page
const MAX_PAGES = 5;         // gentle cap -> at most 125 listings per run
const PAGE_DELAY_MS = 2_000; // pause between page loads — account safety
const pageUrl = (start: number) =>
  `https://www.linkedin.com/jobs/search-results/?${PARAMS}&start=${start}`;

// Runs INSIDE the LinkedIn page (DOM context) via executeScript, so it must be
// fully self-contained: no imports, no outer-scope refs. Reads ONLY the rendered
// results list -- it never opens a job. LinkedIn's markup changes often and the
// class names are obfuscated, so these selectors are best-effort with fallbacks;
// if a run logs 0 cards, update them here (and nothing else).
function scrapeLinkedIn() {
  const text = (root: Element, sel: string) =>
    (root.querySelector(sel) as HTMLElement | null)?.innerText?.trim() || '';

  const cards = document.querySelectorAll(
    'div.job-card-container, li.jobs-search-results__list-item, [data-job-id]'
  );
  const out: Array<{
    jobId: string; title: string; company: string;
    location: string; postedTime: string; easyApply: boolean;
  }> = [];

  cards.forEach((card) => {
    const el = card as HTMLElement;
    const href = (el.querySelector('a[href*="/jobs/view/"]') as HTMLAnchorElement | null)?.href || '';
    const jobId =
      el.getAttribute('data-job-id') ||
      (el.querySelector('[data-job-id]') as HTMLElement | null)?.getAttribute('data-job-id') ||
      href.match(/\/jobs\/view\/(\d+)/)?.[1] ||
      '';
    if (!jobId) return;

    const timeEl = el.querySelector('time') as HTMLElement | null;
    out.push({
      jobId,
      title:
        text(el, '.job-card-list__title') ||
        text(el, 'a.job-card-container__link') ||
        text(el, 'a[href*="/jobs/view/"]'),
      company:
        text(el, '.job-card-container__primary-description') ||
        text(el, '.artdeco-entity-lockup__subtitle') ||
        text(el, '.job-card-container__company-name'),
      location:
        text(el, '.job-card-container__metadata-item') ||
        text(el, '.artdeco-entity-lockup__caption'),
      postedTime: timeEl?.getAttribute('datetime') || timeEl?.innerText?.trim() || '',
      easyApply: /easy apply/i.test(el.innerText),
    });
  });
  return out;
}

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

export const linkedin: Collector = {
  name: NAME,
  host: HOST,
  searchUrl: pageUrl(0),
  async collect(): Promise<NormalizedListing[]> {
    // Walk pages via `start`; dedup across pages (overlap is common). Stop on the
    // first empty page (past the end) or at the gentle MAX_PAGES cap.
    const byId = new Map<string, NormalizedListing>();
    for (let page = 0; page < MAX_PAGES; page++) {
      const raw = await collectViaTab(pageUrl(page * PAGE_SIZE), scrapeLinkedIn);
      if (raw.length === 0) break;
      for (const r of raw) {
        const jobId = String(r.jobId);
        if (byId.has(jobId)) continue;
        byId.set(jobId, {
          key: `${NAME}:${jobId}`,
          source: NAME,
          jobId,
          company: r.company,
          title: r.title,
          location: r.location,
          url: `https://www.linkedin.com/jobs/view/${jobId}/`,
          postedTime: r.postedTime,
          easyApply: r.easyApply,
        });
      }
      if (page < MAX_PAGES - 1) await delay(PAGE_DELAY_MS);
    }
    return [...byId.values()];
  },
};

register(linkedin);
