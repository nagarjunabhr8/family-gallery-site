import { defineConfig, devices } from '@playwright/test'
import { join } from 'node:path'
import { BASE_URL, PORT, PROJECT, prepare, python } from './support/environment'

const world = prepare()

export default defineConfig({
  testDir: './tests',
  // One shared app and library: run in order, one at a time
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
  globalTeardown: './support/teardown.ts',
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: `"${python()}" -m uvicorn app.main:app --host 127.0.0.1 --port ${PORT}`,
    cwd: join(PROJECT, 'backend'),
    url: `${BASE_URL}/api/health`,
    reuseExistingServer: false,
    timeout: 120_000,
    env: { FM_DATA_DIR: world.data },
    stdout: 'ignore',
    stderr: 'pipe',
  },
  projects: [
    {
      name: 'desktop',
      testMatch: /desktop[\\/].*\.spec\.ts/,
      use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 860 } },
    },
    {
      name: 'phone',
      testMatch: /phone[\\/].*\.spec\.ts/,
      dependencies: ['desktop'],
      use: { ...devices['Pixel 7'] },
    },
    {
      name: 'read-only proof',
      testMatch: /readonly\.spec\.ts/,
      dependencies: ['desktop', 'phone'],
    },
  ],
})
