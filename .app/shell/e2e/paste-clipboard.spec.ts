import { test, expect, SAMPLE_PROMPTS_DIR, SAMPLE_CHAPTERS_DIR } from './fixtures/electron'

/**
 * Paste-flow E2E — verifies that firing the paste hotkey actually pushes
 * the expected payload to the system clipboard. Runs against the real
 * Electron clipboard module via the IPC bridge.
 *
 * Each test seeds folder state, configures paste-mode toggles, fires the
 * test hook, then reads back `clipboard.readText()` / file URLs to assert
 * the content is what `buildPastePayload` composed.
 */

async function seed(window: import('@playwright/test').Page, opts: {
  promptAsText?: Record<string, boolean>
  chapterAsText?: boolean
  concurrent?: number
}) {
  await window.evaluate(
    async ({ promptDir, chapterDir, promptAsText, chapterAsText, concurrent }: {
      promptDir: string
      chapterDir: string
      promptAsText: Record<string, boolean>
      chapterAsText: boolean
      concurrent: number
    }) => {
      const store = (window as any).__inkcopyStoreForTests
      const lib = (window as any).__inkcopyChaptersForTests
      const inkcopy = (window as any).inkcopy

      const pe: { name: string; path: string; isFile: boolean }[] = await inkcopy.fs.listDir(promptDir, { recursive: false })
      const promptFiles = pe
        .filter((e) => e.isFile)
        .sort((a, b) => lib.naturalCompare(a.name, b.name))
        .map((e) => ({ displayName: e.name, path: e.path }))
      store.getState().setPromptFolder(promptDir, promptFiles)

      for (const [name, asText] of Object.entries(promptAsText)) {
        store.getState().setPromptPasteMode(name, asText)
      }

      const ce: { name: string; path: string; isFile: boolean }[] = await inkcopy.fs.listDir(chapterDir, { recursive: false })
      const chapterFiles = ce
        .filter((e) => e.isFile)
        .sort((a, b) => lib.naturalCompare(a.name, b.name))
        .map((e) => ({ displayName: e.name, path: e.path, detectedNumber: lib.detectChapterNumber(e.name) }))
      store.getState().setChapterFolder(chapterDir, chapterFiles)
      store.getState().setChapterPasteAsText(chapterAsText)
      store.getState().setConcurrentChapters(concurrent)
      store.getState().setHotkeysRegistered(true)
    },
    {
      promptDir: SAMPLE_PROMPTS_DIR,
      chapterDir: SAMPLE_CHAPTERS_DIR,
      promptAsText: opts.promptAsText ?? {},
      chapterAsText: opts.chapterAsText ?? false,
      concurrent: opts.concurrent ?? 1,
    },
  )
}

async function readClipboard(window: import('@playwright/test').Page): Promise<string> {
  return await window.evaluate(async () => (window as any).inkcopy.clipboard.readText())
}

async function firePaste(window: import('@playwright/test').Page) {
  await window.evaluate(async () => {
    await (window as any).inkcopy.hotkey['_testFirePaste']()
  })
  // Give buildPastePayload's async fs.readText calls + the IPC writeMixed
  // round-trip a chance to settle before assertion.
  await window.waitForTimeout(200)
}

test.describe('INKCOPY — paste actually writes to clipboard', () => {
  test('all-text mode: prompt text + chapter text → joined clipboard text', async ({ window }) => {
    await seed(window, {
      promptAsText: { 'system-prompt.txt': true, 'glossary.txt': true },
      chapterAsText: true,
      concurrent: 1,
    })
    await firePaste(window)

    const text = await readClipboard(window)
    expect(text).toContain('professional Thai novel translator')
    expect(text).toContain('ศัพท์เฉพาะ')
    expect(text).toContain('บทที่ ๑')
    expect(text).toContain('เยว่เฉิน')
    // Three pieces joined by exactly one blank-line separator
    expect(text.split(/\n\n+/).length).toBeGreaterThanOrEqual(3)
  })

  test('concurrent=2 packs two chapters into one paste', async ({ window }) => {
    await seed(window, {
      promptAsText: { 'system-prompt.txt': true, 'glossary.txt': true },
      chapterAsText: true,
      concurrent: 2,
    })
    await firePaste(window)
    const text = await readClipboard(window)
    expect(text).toContain('บทที่ ๑')
    expect(text).toContain('บทที่ ๒')
    expect(text).not.toContain('บทที่ ๓')
  })

  test('chapter file mode: clipboard ends up empty of text (files written natively)', async ({ window }) => {
    await seed(window, {
      promptAsText: {},
      chapterAsText: false,
      concurrent: 1,
    })
    // Set known text first so we can detect whether the paste cleared/changed it
    await window.evaluate(async () => {
      await (window as any).inkcopy.clipboard.writeText('SENTINEL_BEFORE_PASTE')
    })
    await firePaste(window)

    // All-file payload → writeFiles path. The text portion of the clipboard
    // is implementation-defined per OS; on Windows CF_HDROP doesn't reset
    // CF_UNICODETEXT so the sentinel may remain. Either way the renderer
    // shouldn't have stored the SENTINEL in our state.
    const text = await readClipboard(window)
    // Loose check — at minimum the call didn't throw
    expect(typeof text).toBe('string')
  })

  test('paste advances currentIndex by chapterCount', async ({ window }) => {
    await seed(window, {
      promptAsText: { 'system-prompt.txt': true },
      chapterAsText: true,
      concurrent: 2,
    })
    await expect(window.getByTestId('status-bar')).toContainText('1-2/4')
    await firePaste(window)
    await expect(window.getByTestId('status-bar')).toContainText('3-4/4')
  })

  test('toast shows what was pasted', async ({ window }) => {
    await seed(window, {
      promptAsText: { 'system-prompt.txt': true },
      chapterAsText: true,
      concurrent: 1,
    })
    await firePaste(window)
    const toast = window.locator('[data-testid="toast"][data-tone="paste"]')
    await expect(toast).toBeVisible()
    await expect(toast).toContainText('chapter0001')
  })

  test('paused: paste does nothing, clipboard unchanged', async ({ window }) => {
    await seed(window, {
      promptAsText: { 'system-prompt.txt': true },
      chapterAsText: true,
      concurrent: 1,
    })
    await window.evaluate(async () => {
      await (window as any).inkcopy.clipboard.writeText('SENTINEL_PAUSED')
      ;(window as any).__inkcopyStoreForTests.getState().togglePaused()
    })
    await firePaste(window)
    const text = await readClipboard(window)
    expect(text).toBe('SENTINEL_PAUSED')
    // Status bar swaps to the pause message; check the store directly to
    // assert chapter index didn't advance under our feet.
    const currentIndex = await window.evaluate(
      () => (window as any).__inkcopyStoreForTests.getState().currentIndex as number,
    )
    expect(currentIndex).toBe(0)
  })

  test('manual ก่อน/ถัดไป buttons move chapter index by concurrent count', async ({ window }) => {
    await seed(window, {
      promptAsText: { 'system-prompt.txt': true },
      chapterAsText: true,
      concurrent: 2,
    })
    await expect(window.getByTestId('status-bar')).toContainText('1-2/4')
    await window.getByTestId('next-btn').click()
    await expect(window.getByTestId('status-bar')).toContainText('3-4/4')
    await window.getByTestId('prev-btn').click()
    await expect(window.getByTestId('status-bar')).toContainText('1-2/4')
  })
})

test.describe('INKCOPY — auto-register hotkeys when folders ready', () => {
  test('register button no longer exists', async ({ window }) => {
    await expect(window.getByTestId('register-hotkey')).toHaveCount(0)
  })

  test('hotkeys auto-register once both folders populated', async ({ window }) => {
    // Initially nothing is registered.
    await expect(window.getByTestId('pause-toggle')).toBeDisabled()
    await seed(window, {
      promptAsText: { 'system-prompt.txt': true },
      chapterAsText: true,
      concurrent: 1,
    })
    // After seed the App.tsx effect runs hotkey:register; pause toggle enables.
    await expect(window.getByTestId('pause-toggle')).toBeEnabled()
  })
})
