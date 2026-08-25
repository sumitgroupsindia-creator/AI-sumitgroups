import { defineConfig } from 'vitest/config';
import path from 'node:path';

export default defineConfig({
  // Next compiles JSX via SWC; vitest uses esbuild, which needs to be told to use the automatic
  // runtime too, otherwise test files must import React explicitly.
  esbuild: { jsx: 'automatic' },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    include: ['**/*.test.ts', '**/*.test.tsx'],
    exclude: ['node_modules', '.next'],
  },
  resolve: {
    alias: { '@': path.resolve(__dirname, '.') },
  },
});
