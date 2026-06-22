// The one shape the whole extension speaks. Mirrors the pipeline's Listing
// (key, source, company, title, location, url) plus the lightweight list-only
// extras we can read without opening a job. The worker, dedup, and POST bridge
// only ever see this -- never any platform specifics.
export interface NormalizedListing {
  key: string;        // `${source}:${jobId}` — mirrors pipeline Listing.key
  source: string;     // collector name, e.g. "linkedin"
  jobId: string;      // platform job-id — the ONLY dedup key
  company: string;
  title: string;
  location: string;
  url: string;
  postedTime: string; // raw posted text/datetime from the list
  easyApply: boolean;
}

// Every board implements this. Adding a board = one new module that exports a
// Collector and register()s itself — nothing else changes.
export interface Collector {
  readonly name: string;      // unique; also stamped as `source`
  readonly host: string;      // e.g. "www.linkedin.com" (must match a host_permission)
  readonly searchUrl: string; // logged-in job-search results URL (list view)
  collect(): Promise<NormalizedListing[]>;
}
