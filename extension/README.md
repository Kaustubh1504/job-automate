# Job Collector (Chrome MV3 extension)

Background extension that collects **lightweight** job listings from your
**logged-in** job boards and POSTs new ones to the local pipeline endpoint.
Reuses your existing session via host permissions — no separate auth. Reads only
the results **list** (title, company, location, job-id, posted time, Easy-Apply);
never opens per-job pages. Gentle by design: ~45 min cadence + jitter.

## Architecture (extensibility first)
- **`lib/types.ts`** — `Collector` interface + `NormalizedListing` (mirrors the
  pipeline's Listing). The worker/dedup/bridge only ever see these.
- **`lib/registry.ts`** — self-registering provider registry.
- **`lib/poller.ts` / `storage.ts` / `bridge.ts` / `tab.ts`** — fully
  provider-agnostic: collect → dedup by job-id → log → POST.
- **`lib/collectors/`** — one module per board. **LinkedIn is implemented**;
  Indeed / Handshake / NUworks are drop-in stubs.

### Add a new board (the whole point)
1. Copy `lib/collectors/linkedin.ts` → `yourboard.ts`; implement a
   self-contained scrape function + `collect()`; `register()` it.
2. Add `import './yourboard';` to `lib/collectors/index.ts`.
3. Add its host to `host_permissions` in `wxt.config.ts`.

Nothing in the worker, dedup, storage, or bridge changes.

## Build & load
```bash
npm install
npm run build            # -> .output/chrome-mv3/
```
Then in Chrome: `chrome://extensions` → enable **Developer mode** → **Load
unpacked** → select `.output/chrome-mv3/`.
(Or `npm run dev` for an auto-reloading dev build.)

## Test it
1. Be **logged into LinkedIn** in the same Chrome profile.
2. Click the extension icon → **Run now**.
3. Open the **service worker console**: `chrome://extensions` → the extension →
   "Inspect views: service worker". You'll see:
   `[linkedin] found N, new M  [ …listings… ]` and the POST result.

A background LinkedIn tab opens briefly, gets scraped, and closes — that's
expected. If `found 0`, LinkedIn's DOM changed: update the selectors in
`linkedin.ts` (only that file).

## POST receiver (optional, to verify the bridge)
Default endpoint: `http://localhost:8787/listings`. Console logging works with
no receiver; to see the POSTs, run any local server, e.g.:
```python
# python3 receiver.py
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get('content-length', 0))
        print(self.rfile.read(n).decode())
        self.send_response(200); self.end_headers()
HTTPServer(('localhost', 8787), H).serve_forever()
```
Change the endpoint by setting `endpoint` in `chrome.storage.local`.

## Safety
The ~45-min cadence and list-only reads are intentional for account safety.
Don't poll faster or fetch per-job detail pages.
