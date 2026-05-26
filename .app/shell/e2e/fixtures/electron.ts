import { test as base, _electron as electron, type ElectronApplication, type Page } from '@playwright/test'
import path from 'node:path'
import fs from 'node:fs'
import os from 'node:os'

interface Fixtures {
  electronApp: ElectronApplication
  window: Page
  userDataDir: string
}

const SHELL_DIR = path.resolve(__dirname, '..', '..')

/**
 * Per-test Electron fixture — pattern lifted from INKIDEA's
 * `e2e/helpers/app.cjs`. The two non-obvious tricks that make Electron+
 * Playwright reliable on Windows + Node 24:
 *
 *   1. Pass `--user-data-dir` BEFORE the app directory in args. Some Electron
 *      builds otherwise consume the dir arg into the flag's value.
 *   2. Delete `ELECTRON_RUN_AS_NODE` from the launch env. When that var is
 *      present (some shells/CI runners set it implicitly) Electron interprets
 *      the launcher's `-r loader.js` invocation as pure-Node mode and rejects
 *      Chromium flags like `--remote-debugging-port=0`.
 *
 * Also: `cwd: SHELL_DIR` so the app's relative path resolution (preload,
 * dist/) matches a `pnpm dev` shape.
 */
export const test = base.extend<Fixtures>({
  userDataDir: async ({}, use) => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'inkcopy-e2e-ud-'))
    await use(dir)
    try {
      fs.rmSync(dir, { recursive: true, force: true })
    } catch {
      /* best-effort cleanup */
    }
  },
  electronApp: async ({ userDataDir }, use) => {
    const launchEnv = { ...process.env, INKCOPY_E2E: '1', NODE_ENV: 'production' }
    delete launchEnv.ELECTRON_RUN_AS_NODE

    const app = await electron.launch({
      args: [`--user-data-dir=${userDataDir}`, SHELL_DIR],
      cwd: SHELL_DIR,
      env: launchEnv,
      timeout: 30_000,
    })
    await use(app)
    try {
      await app.close()
    } catch {
      /* already closed */
    }
  },
  window: async ({ electronApp }, use) => {
    const win = await electronApp.firstWindow()
    await win.waitForLoadState('domcontentloaded')
    await win.waitForFunction(() => !!(window as any).__inkcopyStoreForTests, null, { timeout: 30_000 })
    await use(win)
  },
})

export const SAMPLE_PROMPTS_DIR = path.resolve(__dirname, 'sample-data', 'prompts')
export const SAMPLE_CHAPTERS_DIR = path.resolve(__dirname, 'sample-data', 'chapters')
export { expect } from '@playwright/test'
