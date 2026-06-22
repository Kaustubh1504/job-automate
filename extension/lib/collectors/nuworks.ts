import { register } from '../registry';
import type { Collector, NormalizedListing } from '../types';

// Drop-in stub. NUworks is Northeastern's Symplicity CSM; confirm the host +
// search URL when implementing, and add the host to host_permissions.
export const nuworks: Collector = {
  name: 'nuworks',
  host: 'northeastern-csm.symplicity.com',
  searchUrl: 'https://northeastern-csm.symplicity.com/students/app/jobs/search',
  async collect(): Promise<NormalizedListing[]> {
    return []; // not implemented yet
  },
};

register(nuworks);
