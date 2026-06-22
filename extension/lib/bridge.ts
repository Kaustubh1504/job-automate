import { getEndpoint } from './storage';
import type { NormalizedListing } from './types';

// Provider-agnostic POST bridge: ships new normalized listings to the local
// pipeline endpoint. Failure is non-fatal (the run still logs what it found),
// so you can verify standalone via the console even with no receiver running.
export async function postListings(listings: NormalizedListing[]): Promise<void> {
  if (!listings.length) return;
  const endpoint = await getEndpoint();
  try {
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ listings }),
    });
    console.log(`[bridge] POST ${listings.length} listing(s) -> ${endpoint} (${res.status})`);
  } catch (e) {
    console.warn(`[bridge] POST to ${endpoint} failed (is the local receiver up?)`, e);
  }
}
