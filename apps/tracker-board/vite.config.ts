import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'

// @dsect/ui is consumed from the vendor/design-system submodule (file: dependency).
// The submodule ships source, not dist, so we alias the package to its entry
// (which imports the canonical tokens/base/components CSS itself).
const kit = fileURLToPath(new URL('../../vendor/design-system', import.meta.url))

// VITE_TRACKER_SOURCE=api proxies /api to Volt's tracker API (TRACKER_API, default :8787).
const apiTarget = process.env.TRACKER_API ?? 'http://127.0.0.1:7655'
const proxy = { '/api': { target: apiTarget, changeOrigin: true } }

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: [
      { find: /^@dsect\/ui$/, replacement: `${kit}/react/src/index.ts` },
      { find: /^@dsect\/ui\/fonts\.css$/, replacement: `${kit}/fonts.css` },
    ],
    dedupe: ['react', 'react-dom'],
  },
  server: { port: 5174, proxy, fs: { allow: ['..', '../..'] } },
  preview: { port: 4174, proxy },
})
