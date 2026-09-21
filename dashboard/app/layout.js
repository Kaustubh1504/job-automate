import './globals.css';
import Link from 'next/link';
import { Geist, Geist_Mono } from 'next/font/google';
import TabNav from './TabNav';

const geistSans = Geist({ variable: '--font-geist-sans', subsets: ['latin'] });
const geistMono = Geist_Mono({ variable: '--font-geist-mono', subsets: ['latin'] });

export const metadata = { title: 'Job Tracker' };

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
      <body className="bg-gray-50 text-gray-900">
        <nav className="border-b bg-white">
          <div className="mx-auto flex max-w-7xl gap-6 px-4 py-3 text-sm font-medium">
            <span className="font-semibold">Job Tracker</span>
            <Link href="/interns" className="text-blue-600 hover:underline">Jobs</Link>
            <Link href="/config" className="text-blue-600 hover:underline">Config</Link>
            <Link href="/mailer" className="text-blue-600 hover:underline">Mailer</Link>
          </div>
        </nav>
        <main className="mx-auto max-w-7xl px-4 py-6">
          <TabNav />
          {children}
        </main>
      </body>
    </html>
  );
}
