import { redirect } from 'next/navigation';

// The tabs are real routes now; the landing page is the consolidated intern view.
export default function Home() {
  redirect('/interns');
}
