import './globals.css';
import Link from 'next/link';

export const metadata = { title: 'Job Tracker' };

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className="bg-gray-50 text-gray-900">
        <nav className="border-b bg-white">
          <div className="mx-auto flex max-w-7xl gap-6 px-4 py-3 text-sm font-medium">
            <span className="font-semibold">Job Tracker</span>
            <Link href="/" className="text-blue-600 hover:underline">Jobs</Link>
            <Link href="/config" className="text-blue-600 hover:underline">Config</Link>
          </div>
        </nav>
        <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
