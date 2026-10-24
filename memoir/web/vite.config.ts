/// <reference types="vitest" />
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  build: { outDir: '../engine/memoir_engine/static', emptyOutDir: true },
  server: { port: 5173, proxy: { '/api': 'http://127.0.0.1:8787' } },
  test: { environment: 'jsdom', globals: true, setupFiles: ['./src/test/setup.ts'] },
});
