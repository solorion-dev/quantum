import { defineConfig, devices } from '@playwright/test'

// Runs against Volt's local tracker-api (fresh --reset seed, fake data only) + the Vite dev server.
// Set PW_CHROME=/usr/bin/google-chrome to use a system Chrome instead of `npx playwright install chromium`.
const chrome = process.env.PW_CHROME
const launchOptions = chrome ? { executablePath: chrome, args: ['--no-sandbox'] } : {}
export default defineConfig({
  testDir: './e2e',
  workers: 1,
  reporter: [['list']],
  use: { actionTimeout: 8000, baseURL: 'http://localhost:5175', launchOptions },
  projects: [
    { name: 'desktop-1920', use: { ...devices['Desktop Chrome'], viewport: { width: 1920, height: 1080 }, launchOptions } },
    { name: 'phone-390', use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2, launchOptions } },
  ],
  webServer: [
    { command: 'cd ../tracker-api && python3 -m tracker_api --reset --port 7656 --db /tmp/tracker-board-e2e.db', url: 'http://127.0.0.1:7656/api/health', reuseExistingServer: false },
    { command: 'TRACKER_API=http://127.0.0.1:7656 npx vite --port 5175 --strictPort', url: 'http://localhost:5175', reuseExistingServer: false },
  ],
})
