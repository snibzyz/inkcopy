import { test, expect } from './fixtures/electron'
import path from 'node:path'

const SAMPLE_PROMPTS = path.resolve(__dirname, 'fixtures', 'sample-data', 'prompts')
const SAMPLE_CHAPTERS = path.resolve(__dirname, 'fixtures', 'sample-data', 'chapters')

/**
 * Visual regression suite — captures one screenshot per major UI state so
 * accidental regressions to spacing/color/icons are caught in CI. Baselines
 * are committed under e2e/__screenshots__/ and updated via
 * `pnpm test:e2e -- --update-snapshots`.
 *
 * threshold/maxDiffPixelRatio are generous: the dev environment renders fonts
 * slightly differently than CI, and we care about layout regressions not
 * sub-pixel anti-aliasing changes.
 */
const SNAPSHOT_OPTS = {
  maxDiffPixelRatio: 0.04,
  threshold: 0.25,
  animations: 'disabled' as const,
}

async function seedSampleData(window: import('@playwright/test').Page) {
  await window.evaluate(
    async ({ promptDir, chapterDir }: { promptDir: string; chapterDir: string }) => {
      const store = (window as any).__inkcopyStoreForTests
      const lib = (window as any).__inkcopyChaptersForTests
      const inkcopy = (window as any).inkcopy

      const pe: { name: string; path: string; isFile: boolean }[] = await inkcopy.fs.listDir(promptDir, { recursive: false })
      const promptFiles = pe
        .filter((e) => e.isFile)
        .sort((a, b) => lib.naturalCompare(a.name, b.name))
        .map((e) => ({ displayName: e.name, path: e.path }))
      store.getState().setPromptFolder(promptDir, promptFiles)

      const ce: { name: string; path: string; isFile: boolean }[] = await inkcopy.fs.listDir(chapterDir, { recursive: false })
      const chapterFiles = ce
        .filter((e) => e.isFile)
        .sort((a, b) => lib.naturalCompare(a.name, b.name))
        .map((e) => ({ displayName: e.name, path: e.path, detectedNumber: lib.detectChapterNumber(e.name) }))
      store.getState().setChapterFolder(chapterDir, chapterFiles)
    },
    { promptDir: SAMPLE_PROMPTS, chapterDir: SAMPLE_CHAPTERS },
  )
}

test.describe('INKCOPY — visual regression', () => {
  test('empty PASTE mode (no folders selected)', async ({ window }) => {
    await expect(window).toHaveScreenshot('paste-empty.png', SNAPSHOT_OPTS)
  })

  test('PASTE mode with sample folders loaded', async ({ window }) => {
    await seedSampleData(window)
    await expect(window).toHaveScreenshot('paste-loaded.png', SNAPSHOT_OPTS)
  })

  test('COPY mode shows output section', async ({ window }) => {
    await window.getByTestId('mode-copy').click()
    await expect(window).toHaveScreenshot('copy-empty.png', SNAPSHOT_OPTS)
  })

  test('VOCAB mode shows vocab filename input', async ({ window }) => {
    await window.getByTestId('mode-vocab').click()
    await expect(window).toHaveScreenshot('vocab-empty.png', SNAPSHOT_OPTS)
  })

  test('minimized overlay shows current chapter inline', async ({ window }) => {
    await seedSampleData(window)
    await window.getByTestId('minimize-toggle').click()
    await expect(window.getByTestId('minimized-status')).toBeVisible()
    await expect(window).toHaveScreenshot('minimized.png', SNAPSHOT_OPTS)
  })

  test('mode toggle button states', async ({ window }) => {
    await expect(window.locator('.grid.grid-cols-3').first()).toHaveScreenshot('mode-toggle.png', SNAPSHOT_OPTS)
  })

  test('diagnostics row when hotkey not registered', async ({ window }) => {
    await expect(window.locator('[data-testid="status-bar"] + div').first()).toHaveScreenshot('diagnostics.png', SNAPSHOT_OPTS)
  })
})
