import type { Collector } from './types';

// Self-registering provider registry — same pattern as the pipeline's parser
// registry. Collector modules call register() at import; the worker only ever
// asks for getCollectors(), never knowing which boards exist.
const registry = new Map<string, Collector>();

export function register(collector: Collector): void {
  registry.set(collector.name, collector);
}

export function getCollectors(): Collector[] {
  return [...registry.values()];
}
