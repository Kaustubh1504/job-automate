import { defineConfig } from 'wxt';

// WXT generates the MV3 manifest from the entrypoints + this config.
export default defineConfig({
  manifest: {
    name: 'Job Collector',
    description: 'Collects lightweight job listings from logged-in job boards.',
    permissions: ['alarms', 'storage', 'scripting', 'tabs'],
    host_permissions: [
      'https://www.linkedin.com/*', // linkedin collector (scripting on its tab)
      'http://localhost/*',         // POST bridge -> local pipeline endpoint (any port)
      // Adding a board = implement its collector module AND add one line here:
      // 'https://www.indeed.com/*',
      // 'https://app.joinhandshake.com/*',
      // 'https://northeastern-csm.symplicity.com/*',
    ],
  },
});
