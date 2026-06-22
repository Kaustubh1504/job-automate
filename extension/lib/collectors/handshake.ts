import { register } from '../registry';
import type { Collector, NormalizedListing } from '../types';

// Drop-in stub. Implement like linkedin.ts and add the host to host_permissions.
export const handshake: Collector = {
  name: 'handshake',
  host: 'app.joinhandshake.com',
  searchUrl: 'https://app.joinhandshake.com/job-search',
  async collect(): Promise<NormalizedListing[]> {
    return []; // not implemented yet
  },
};

register(handshake);
