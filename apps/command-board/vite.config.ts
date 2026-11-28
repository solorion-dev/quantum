/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// The Command Board UI talks to services/command-board (default
// 127.0.0.1:8798) through the dev proxy so the app is same-origin in dev,
// matching the TRK-0660 same-origin discipline. In production the app is
// served behind the Solorion login seam on the same origin as the API.
// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    exclude: ['e2e/**', 'node_modules/**', 'dist/**'],
  },
  server: {
    port: 5179,
    host: '127.0.0.1',
    proxy: {
      '/api': {
        target: process.env.BOARD_API_URL || 'http://127.0.0.1:8798',
        changeOrigin: true,
      },
    },
  },
  preview: {
    port: 4179,
    host: '127.0.0.1',
  },
});
