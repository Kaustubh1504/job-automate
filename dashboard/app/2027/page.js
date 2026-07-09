import InternView from '../interns/InternView';

// Curated Summer 2027 shortlist for a friend: every intern role marked Referral,
// across all boards. Ticking the Referral box on any tab adds a role here;
// unticking it removes it.
export default function Page() {
  return <InternView referredOnly />;
}
