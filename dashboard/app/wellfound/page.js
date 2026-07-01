import { Suspense } from 'react';
import WellfoundView from './WellfoundView';

// Suspense boundary: WellfoundView reads ?batch= via useSearchParams.
export default function Page() {
  return (
    <Suspense>
      <WellfoundView />
    </Suspense>
  );
}
