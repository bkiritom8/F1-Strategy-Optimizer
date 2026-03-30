/**
 * @file __tests__/setup.ts
 * @description Vitest global setup. Adds @testing-library/jest-dom matchers.
 */

import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';

// Mock sessionStorage for API client tests
const store: Record<string, string> = {};
Object.defineProperty(globalThis, 'sessionStorage', {
  value: {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, val: string) => { store[key] = val; },
    removeItem: (key: string) => { delete store[key]; },
    clear: () => { Object.keys(store).forEach((k) => delete store[k]); },
  },
});

afterEach(() => {
  sessionStorage.clear();
});
