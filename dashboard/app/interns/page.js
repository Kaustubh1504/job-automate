import { Suspense } from 'react';
import InternView from './InternView';

// Suspense boundary: InternView reads ?batch= via useSearchParams (the Discord
// deep-link), which Next requires to be wrapped.
export default function Page() {
  return (
    <Suspense>
      <InternView />
    </Suspense>
  );
}
