import { Suspense } from 'react';
import JobsTableView from '../jobs/JobsTableView';

// Suspense boundary: JobsTableView reads ?batch= via useSearchParams (the Discord
// deep-link), which Next requires to be wrapped.
export default function Page() {
  return (
    <Suspense>
      <JobsTableView role="all" />
    </Suspense>
  );
}
