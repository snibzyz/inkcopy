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
  // After paste: advance runs synchronously, then the pre-load effect
  // re-writes the clipboard async with the NEXT chapter's payload. Wait long
  // enough for that round-trip to settle.
  await window.waitForTimeout(300)
}

/** Wait until the pre-load clipboard write completes after seeding state. */
async function waitForPreload(window: import('@playwright/test').Page) {
  await window.waitForTimeout(300)
}

test.describe('INKCOPY — clipboard pre-load (Python-style)', () => {
  test('all-text mode: prompt + chapter pre-loaded on seed (before any paste)', async ({ window }) => {
    await seed(window, {
      promptAsText: { 'system-prompt.txt': true, 'glossary.txt': true },
      chapterAsText: true,
      concurrent: 1,
    })
    await waitForPreload(window)

    // Clipboard should already contain chapter 1's payload before the user
    // even presses Cmd+V — the pre-load effect ran after seed.
    const text = await readClipboard(window)
    expect(text).toContain('professional Thai novel translator')
    expect(text).toContain('ศัพท์เฉพาะ')
    expect(text).toContain('บทที่ ๑')
    expect(text).toContain('เยว่เฉิน')
    expect(text.split(/\n\n+/).length).toBeGreaterThanOrEqual(3)
  })

  test('concurrent=2: clipboard pre-loaded with chapters 1+2 (not 3)', async ({ window }) => {
    await seed(window, {
      promptAsText: { 'system-prompt.txt': true, 'glossary.txt': true },
      chapterAsText: true,
      concurrent: 2,
    })
    await waitForPreload(window)
    const text = await readClipboard(window)
    expect(text).toContain('บทที่ ๑')
    expect(text).toContain('บทที่ ๒')
    expect(text).not.toContain('บทที่ ๓')
  })

  test('after firePaste: clipboard rotates to NEXT chapter (chapter 2)', async ({ window }) => {
    await seed(window, {
      promptAsText: { 'system-prompt.txt': true, 'glossary.txt': true },
      chapterAsText: true,
      concurrent: 1,
    })
    await waitForPreload(window)
    await firePaste(window)

    const text = await readClipboard(window)
    // After paste, the pre-load effect re-armed with chapter 2.
    expect(text).toContain('บทที่ ๒')
    expect(text).not.toContain('บทที่ ๑')
  })

  test('chapter file mode: clipboard writeFiles call did not throw', async ({ window }) => {
    await seed(window, {
      promptAsText: {},
      chapterAsText: false,
      concurrent: 1,
    })
    await waitForPreload(window)
    const text = await readClipboard(window)
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
      // All-text so the sentinel comes from clipboard.writeText (single
      // CF_UNICODETEXT format). Mixed mode on Windows ends up CF_HDROP-only
      // because the text portion currently lives only on the macOS branch.
      promptAsText: { 'system-prompt.txt': true, 'glossary.txt': true },
      chapterAsText: true,
      concurrent: 1,
    })
    // Let the initial pre-load complete + drain, otherwise the async
    // fs.readText round-trip may finish AFTER we write SENTINEL and clobber it.
    await waitForPreload(window)
    await window.evaluate(async () => {
      ;(window as any).__inkcopyStoreForTests.getState().togglePaused()
    })
    // After pause toggle, the effect's writeIfNeeded sees paused=true and
    // returns without writing — clipboard is "frozen" with the chapter 1
    // content. Use that as our SENTINEL instead of writing one in.
    const sentinel = await readClipboard(window)
    expect(sentinel.length).toBeGreaterThan(0)
    await firePaste(window)
    const text = await readClipboard(window)
    // Clipboard should not have been touched while paused — content matches
    // the frozen sentinel from before the toggle.
    expect(text).toBe(sentinel)
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

test.describe('INKCOPY — staged mixed auto-switch (text → files → synthetic → advance)', () => {
  test('prompt-text + chapter-file: one paste runs the full swap and advances exactly once', async ({ window }) => {
    // Mixed: prompt as TEXT, chapter as FILE → the "true auto-switch" path.
    await seed(window, { promptAsText: { 'system-prompt.txt': true, 'glossary.txt': true }, chapterAsText: false, concurrent: 1 })
    // Shrink the staged delays so the test is fast (defaults are 450ms each on mac).
    await window.evaluate(() => {
      ;(window as any).__inkcopyStoreForTests.setState({
        stagedMsAfterUserPaste: 10,
        stagedMsClipboardToCtrlV: 10,
        stagedMsAfterTextPaste: 10,
      })
    })
    await waitForPreload(window)

    // Pre-paste: clipboard holds the prompt TEXT and the chapter file is staged.
    const before = await window.evaluate(() => {
      const s = (window as any).__inkcopyStoreForTests.getState()
      return { staged: s.stagedPendingFilePaths, ci: s.currentIndex }
    })
    expect(before.ci).toBe(0)
    expect(before.staged).toHaveLength(1)
    expect(before.staged[0]).toContain('chapter0001.txt')
    expect(await readClipboard(window)).toContain('professional Thai novel translator')

    // One Cmd+V → swap to files → synthetic paste (e2e-stubbed ok) → advance.
    await window.evaluate(async () => { await (window as any).inkcopy.hotkey['_testFirePaste']() })
    await window.waitForTimeout(500)

    const after = await window.evaluate(() => {
      const s = (window as any).__inkcopyStoreForTests.getState()
      return { staged: s.stagedPendingFilePaths, ci: s.currentIndex, active: s.stagedSequenceActive }
    })
    // currentIndex only advances inside finishAdvance, which runs AFTER the
    // swap + synthetic paste succeed — so ci===1 proves the whole chain ran,
    // and ===1 (not 2) proves no double-advance.
    expect(after.ci).toBe(1)
    expect(after.active).toBe(false)
    // Re-armed for the next round: chapter 2 staged, prompt text on clipboard.
    expect(after.staged).toHaveLength(1)
    expect(after.staged[0]).toContain('chapter0002.txt')
    expect(await readClipboard(window)).toContain('professional Thai novel translator')
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
