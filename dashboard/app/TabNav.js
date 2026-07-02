'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

// Shared tab bar across the job views. Each tab is a real route (deep-linkable,
// back/forward works); the active one is derived from the current path. Rendered
// once in the root layout, it hides itself on non-job pages (e.g. /config).
const TABS = [
  { href: '/interns', label: 'All Interns' },
  { href: '/all', label: 'All' },
  { href: '/jobright', label: 'Jobright' },
  { href: '/jobspy', label: 'JobSpy' },
  { href: '/handshake', label: 'Handshake' },
  { href: '/wellfound', label: 'Wellfound' },
  { href: '/newgrad', label: 'New Grad' },
  { href: '/2027', label: '2027' },
];

export default function TabNav() {
  const pathname = usePathname();
  if (!TABS.some((t) => pathname === t.href)) return null; // only on job routes

  return (
    <div className="mb-4 flex gap-1 border-b">
      {TABS.map((t) => {
        const active = pathname === t.href;
        return (
          <Link
            key={t.href}
            href={t.href}
            className={`-mb-px border-b-2 px-4 py-2 text-sm ${
              active
                ? 'border-blue-600 font-medium text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-800'
            }`}
          >
            {t.label}
          </Link>
        );
      })}
    </div>
  );
}
