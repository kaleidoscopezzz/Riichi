import { defineConfig } from '@playwright/test'

const origin = process.env.RIICHI_QA_URL
if (!origin || !/^https:\/\/localhost:\d+$/.test(origin) || !process.env.RIICHI_QA_CREDENTIALS)
  throw new Error('Browser writes require an isolated localhost HTTPS QA environment.')

export default defineConfig({
  testDir: './e2e',
  timeout: 600_000,
  globalTimeout: 900_000,
  workers: 1,
  retries: 0,
  forbidOnly: !!process.env.CI,
  outputDir: '../.verification/production-launch/browser',
  reporter: [['list']],
  use: {
    baseURL: origin,
    browserName: 'chromium',
    viewport: { width: 1440, height: 1000 },
    // Only the guarded loopback QA origin uses a private CA. Public production
    // verification is separate, with the system trust store and no bypass.
    ignoreHTTPSErrors: true,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
})
