import { Suspense } from 'react';
import HandshakeView from './HandshakeView';

// Suspense boundary: HandshakeView reads ?batch= via useSearchParams.
export default function Page() {
  return (
    <Suspense>
      <HandshakeView />
    </Suspense>
  );
}
