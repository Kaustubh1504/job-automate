import { Suspense } from 'react';
import JobspyView from './JobspyView';

// Suspense boundary: JobspyView reads ?batch= via useSearchParams (the Discord
// deep-link), which Next requires to be wrapped.
export default function Page() {
  return (
    <Suspense>
      <JobspyView />
    </Suspense>
  );
}
