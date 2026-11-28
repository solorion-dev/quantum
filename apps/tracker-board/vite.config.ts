import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// The /api proxy targets the live tracker-board service (Tritium :7654),
// which serves item detail (GET /api/item/<id>) and edits
// (POST /api/item/<id>/update). The board list itself comes from the
// snapshot at /board-data.json (see scripts/snapshot-board.py) — the
// service has no list endpoint. Override the target with TRACKER_API,
// e.g. TRACKER_API=http://100.66.182.7:7654 (Tritium tailnet IP).
const apiTarget = process.env.TRACKER_API ?? 'http://127.0.0.1:7654';
const apiProxy = { '/api': { target: apiTarget, changeOrigin: true } };

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5174, proxy: apiProxy },
  preview: { port: 4174, proxy: apiProxy },
});
