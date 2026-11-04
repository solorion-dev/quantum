import { defineConfig, devices } from '@playwright/test'

// Runs against Volt's local tracker-api (fresh --reset seed, fake data only) + the Vite dev server.
// Set PW_CHROME=/usr/bin/google-chrome to use a system Chrome instead of `npx playwright install chromium`.
const chrome = process.env.PW_CHROME
// Ports are overridable so parallel agents' servers never collide (PW_API_PORT / PW_WEB_PORT).
const apiPort = process.env.PW_API_PORT ?? '7656'
const webPort = process.env.PW_WEB_PORT ?? '5175'
const launchOptions = chrome ? { executablePath: chrome, args: ['--no-sandbox'] } : {}
export default defineConfig({
  testDir: './e2e',
  workers: 1,
  reporter: [['list']],
  use: { actionTimeout: 8000, baseURL: `http://localhost:${webPort}`, launchOptions },
  projects: [
    { name: 'desktop-1920', use: { ...devices['Desktop Chrome'], viewport: { width: 1920, height: 1080 }, launchOptions } },
    { name: 'phone-390', use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2, launchOptions } },
  ],
  webServer: [
    { command: `cd ../tracker-api && python3 -m tracker_api --reset --port ${apiPort} --db /tmp/tracker-board-e2e-${apiPort}.db`, url: `http://127.0.0.1:${apiPort}/api/health`, reuseExistingServer: false },
    { command: `TRACKER_API=http://127.0.0.1:${apiPort} npx vite --port ${webPort} --strictPort`, url: `http://localhost:${webPort}`, reuseExistingServer: false },
  ],
})
