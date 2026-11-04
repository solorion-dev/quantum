import { defineConfig, devices } from '@playwright/test'

// Runs against Volt's local tracker-api (fresh --reset seed, fake data only) + the Vite dev server.
// Set PW_CHROME=/usr/bin/google-chrome to use a system Chrome instead of `npx playwright install chromium`.
const chrome = process.env.PW_CHROME
const API_PORT = process.env.TB_API_PORT || '7656'
const WEB_PORT = process.env.TB_WEB_PORT || '5175'
const launchOptions = chrome ? { executablePath: chrome, args: ['--no-sandbox'] } : {}
export default defineConfig({
  testDir: './e2e',
  workers: 1,
  reporter: [['list']],
  use: { actionTimeout: 8000, baseURL: `http://localhost:${WEB_PORT}`, launchOptions },
  projects: [
    { name: 'desktop-1920', use: { ...devices['Desktop Chrome'], viewport: { width: 1920, height: 1080 }, launchOptions } },
    { name: 'phone-390', use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2, launchOptions } },
  ],
  webServer: [
    { command: `cd ../tracker-api && TRACKER_WEBHOOK_SECRET=e2e-test-only-fake python3 -m tracker_api --reset --port ${API_PORT} --db /tmp/tracker-board-e2e-${API_PORT}.db`, url: `http://127.0.0.1:${API_PORT}/api/health`, reuseExistingServer: false },
    { command: `TRACKER_API=http://127.0.0.1:${API_PORT} npx vite --port ${WEB_PORT} --strictPort`, url: `http://localhost:${WEB_PORT}`, reuseExistingServer: false },
  ],
})
