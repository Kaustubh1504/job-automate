import { Suspense } from 'react';
import JobrightView from './JobrightView';

// Suspense boundary: JobrightView reads ?batch= via useSearchParams.
export default function Page() {
  return (
    <Suspense>
      <JobrightView />
    </Suspense>
  );
}
