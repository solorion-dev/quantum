import { defineConfig } from '@playwright/test';

// E2E expects both halves running locally:
//   services/command-board  -> http://127.0.0.1:8798  (npm run dev)
//   apps/command-board      -> http://127.0.0.1:5179  (npm run dev)
// Start them first, then: npm run test:e2e
export default defineConfig({
  testDir: './e2e',
  timeout: 120000,
  expect: {
    timeout: 15000,
  },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    browserName: 'chromium',
    baseURL: process.env.BOARD_UI_URL || 'http://127.0.0.1:5179',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'Chromium Mobile 390x844',
      use: {
        browserName: 'chromium',
        viewport: { width: 390, height: 844 },
      },
    },
    {
      name: 'Chromium Desktop 1280x800',
      use: {
        browserName: 'chromium',
        viewport: { width: 1280, height: 800 },
      },
    },
  ],
});
