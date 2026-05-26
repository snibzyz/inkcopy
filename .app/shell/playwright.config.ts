import { defineConfig } from '@playwright/test'

/**
 * Headful Electron E2E config — mirrors the pattern used by other INK family
 * apps (single project, no Playwright browsers; the Electron app process
 * itself is launched per-test via electron.launch()).
 *
 * Each test gets its own clean userData via the fixture in fixtures/electron.ts.
 * INKCOPY_E2E=1 exposes the hotkey:_testFire* IPC handlers that simulate
 * Cmd/Ctrl+V without the native module being wired in.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false, // Electron windows fight over focus when parallel
  workers: 1,
  retries: 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  timeout: 45_000,
  expect: { timeout: 6_000 },
  use: {
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
})
