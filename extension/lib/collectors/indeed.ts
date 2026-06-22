import { register } from '../registry';
import type { Collector, NormalizedListing } from '../types';

// Drop-in stub. To implement: copy linkedin.ts's shape -- a self-contained
// scrapeIndeed() reading the results list, then collectViaTab(SEARCH_URL, ...).
// Also add 'https://www.indeed.com/*' to host_permissions in wxt.config.ts.
export const indeed: Collector = {
  name: 'indeed',
  host: 'www.indeed.com',
  searchUrl: 'https://www.indeed.com/jobs?q=software+engineer&sort=date',
  async collect(): Promise<NormalizedListing[]> {
    return []; // not implemented yet
  },
};

register(indeed);
