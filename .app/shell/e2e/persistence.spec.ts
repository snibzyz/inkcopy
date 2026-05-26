import { test, expect, SAMPLE_PROMPTS_DIR, SAMPLE_CHAPTERS_DIR } from './fixtures/electron'
import path from 'node:path'
import fs from 'node:fs'

/**
 * Persistence E2E — verifies <userData>/settings.json is written when the
 * user picks folders / changes settings, and that a fresh app launch picks
 * up where they left off. The fixture's `userDataDir` is a temp dir per
 * test, so settings.json paths can be inspected directly.
 *
 * Mirrors the Python load_config / save_config contract from inkcopy.py:
 * the user shouldn't have to re-pick folders on every launch.
 */

test.describe('INKCOPY — settings.json persistence', () => {
  test('seeding folders writes settings.json with both paths', async ({ window, userDataDir }) => {
    await window.evaluate(
      async ({ promptDir, chapterDir }: { promptDir: string; chapterDir: string }) => {
        const store = (window as any).__inkcopyStoreForTests
        const lib = (window as any).__inkcopyChaptersForTests
        const inkcopy = (window as any).inkcopy
        const pe: { name: string; path: string; isFile: boolean }[] = await inkcopy.fs.listDir(promptDir, { recursive: false })
        store.getState().setPromptFolder(
          promptDir,
          pe.filter((e) => e.isFile).sort((a, b) => lib.naturalCompare(a.name, b.name)).map((e) => ({ displayName: e.name, path: e.path })),
        )
        const ce: { name: string; path: string; isFile: boolean }[] = await inkcopy.fs.listDir(chapterDir, { recursive: false })
        store.getState().setChapterFolder(
          chapterDir,
          ce.filter((e) => e.isFile).sort((a, b) => lib.naturalCompare(a.name, b.name)).map((e) => ({
            displayName: e.name,
            path: e.path,
            detectedNumber: lib.detectChapterNumber(e.name),
          })),
        )
        store.getState().setConcurrentChapters(3)
        store.getState().setMode('copy')
      },
      { promptDir: SAMPLE_PROMPTS_DIR, chapterDir: SAMPLE_CHAPTERS_DIR },
    )

    // Autosave debounce is 300ms — give it a beat to flush.
    await window.waitForTimeout(500)

    const settingsPath = path.join(userDataDir, 'settings.json')
    expect(fs.existsSync(settingsPath)).toBe(true)
    const persisted = JSON.parse(fs.readFileSync(settingsPath, 'utf-8'))
    expect(persisted.promptFolder).toBe(SAMPLE_PROMPTS_DIR)
    expect(persisted.chapterFolder).toBe(SAMPLE_CHAPTERS_DIR)
    expect(persisted.promptFilePaths).toHaveLength(2)
    expect(persisted.concurrentChapters).toBe(3)
    expect(persisted.mode).toBe('copy')
  })

  test('per-prompt paste-mode toggle persists across the autosave debounce', async ({ window, userDataDir }) => {
    await window.evaluate(
      async ({ promptDir }: { promptDir: string }) => {
        const store = (window as any).__inkcopyStoreForTests
        const lib = (window as any).__inkcopyChaptersForTests
        const inkcopy = (window as any).inkcopy
        const pe: { name: string; path: string; isFile: boolean }[] = await inkcopy.fs.listDir(promptDir, { recursive: false })
        store.getState().setPromptFolder(
          promptDir,
          pe.filter((e) => e.isFile).sort((a, b) => lib.naturalCompare(a.name, b.name)).map((e) => ({ displayName: e.name, path: e.path })),
        )
        store.getState().setPromptPasteMode('glossary.txt', true)
        store.getState().setPromptPasteMode('system-prompt.txt', false)
      },
      { promptDir: SAMPLE_PROMPTS_DIR },
    )
    await window.waitForTimeout(500)
    const settingsPath = path.join(userDataDir, 'settings.json')
    const persisted = JSON.parse(fs.readFileSync(settingsPath, 'utf-8'))
    expect(persisted.promptPasteModes['glossary.txt']).toBe(true)
    expect(persisted.promptPasteModes['system-prompt.txt']).toBe(false)
  })
})

test.describe('INKCOPY — hydration on next launch', () => {
  test('relaunching with prior settings restores folders + lists files from disk', async ({ window, userDataDir, electronApp }) => {
    // ── Session 1: seed + autosave
    await window.evaluate(
      async ({ promptDir, chapterDir }: { promptDir: string; chapterDir: string }) => {
        const store = (window as any).__inkcopyStoreForTests
        const lib = (window as any).__inkcopyChaptersForTests
        const inkcopy = (window as any).inkcopy
        const pe: { name: string; path: string; isFile: boolean }[] = await inkcopy.fs.listDir(promptDir, { recursive: false })
        store.getState().setPromptFolder(
          promptDir,
          pe.filter((e) => e.isFile).map((e) => ({ displayName: e.name, path: e.path })),
        )
        const ce: { name: string; path: string; isFile: boolean }[] = await inkcopy.fs.listDir(chapterDir, { recursive: false })
        store.getState().setChapterFolder(
          chapterDir,
          ce.filter((e) => e.isFile).sort((a, b) => lib.naturalCompare(a.name, b.name)).map((e) => ({
            displayName: e.name,
            path: e.path,
            detectedNumber: lib.detectChapterNumber(e.name),
          })),
        )
        store.getState().setCurrentIndex(2)
        store.getState().setChapterPasteAsText(true)
        store.getState().setConcurrentChapters(2)
      },
      { promptDir: SAMPLE_PROMPTS_DIR, chapterDir: SAMPLE_CHAPTERS_DIR },
    )
    await window.waitForTimeout(500) // autosave flush

    // ── Session 2: close + relaunch the same userDataDir manually so the
    // hydrate effect picks up settings.json. We can't reuse the fixture's
    // launcher because it spawns a brand-new userDataDir; manage one app
    // manually here.
    await electronApp.close()

    const { _electron: electron } = await import('@playwright/test')
    const path2 = await import('node:path')
    const SHELL_DIR = path2.resolve(__dirname, '..')
    const launchEnv = { ...process.env, INKCOPY_E2E: '1', NODE_ENV: 'production' }
    delete launchEnv.ELECTRON_RUN_AS_NODE
    const app2 = await electron.launch({
      args: [`--user-data-dir=${userDataDir}`, SHELL_DIR],
      cwd: SHELL_DIR,
      env: launchEnv,
      timeout: 30_000,
    })
    const win2 = await app2.firstWindow()
    await win2.waitForLoadState('domcontentloaded')
    await win2.waitForFunction(() => !!(window as any).__inkcopyStoreForTests, null, { timeout: 30_000 })
    // Allow hydrateFromSettings to complete (it's async — re-lists folders).
    await win2.waitForFunction(
      () => (window as any).__inkcopyStoreForTests.getState().chapterFiles.length > 0,
      null,
      { timeout: 10_000 },
    )

    const restored = await win2.evaluate(() => {
      const s = (window as any).__inkcopyStoreForTests.getState()
      return {
        promptFolder: s.promptFolder,
        promptCount: s.promptFiles.length,
        chapterFolder: s.chapterFolder,
        chapterCount: s.chapterFiles.length,
        currentIndex: s.currentIndex,
        chapterPasteAsText: s.chapterPasteAsText,
        concurrentChapters: s.concurrentChapters,
      }
    })
    expect(restored.promptFolder).toBe(SAMPLE_PROMPTS_DIR)
    expect(restored.promptCount).toBe(2)
    expect(restored.chapterFolder).toBe(SAMPLE_CHAPTERS_DIR)
    expect(restored.chapterCount).toBe(4)
    expect(restored.currentIndex).toBe(2)
    expect(restored.chapterPasteAsText).toBe(true)
    expect(restored.concurrentChapters).toBe(2)
    await app2.close()
  })

  test('missing folder on hydrate is dropped gracefully', async ({ window, userDataDir, electronApp }) => {
    // Write a settings.json pointing at a folder that doesn't exist.
    const settingsPath = path.join(userDataDir, 'settings.json')
    fs.mkdirSync(userDataDir, { recursive: true })
    fs.writeFileSync(
      settingsPath,
      JSON.stringify({
        promptFolder: 'C:\\definitely-not-a-folder-' + Date.now(),
        chapterFolder: 'C:\\also-gone-' + Date.now(),
        concurrentChapters: 7,
      }),
      'utf-8',
    )
    await electronApp.close()

    const { _electron: electron } = await import('@playwright/test')
    const path2 = await import('node:path')
    const SHELL_DIR = path2.resolve(__dirname, '..')
    const launchEnv = { ...process.env, INKCOPY_E2E: '1', NODE_ENV: 'production' }
    delete launchEnv.ELECTRON_RUN_AS_NODE
    const app2 = await electron.launch({
      args: [`--user-data-dir=${userDataDir}`, SHELL_DIR],
      cwd: SHELL_DIR,
      env: launchEnv,
      timeout: 30_000,
    })
    const win2 = await app2.firstWindow()
    await win2.waitForLoadState('domcontentloaded')
    await win2.waitForFunction(() => !!(window as any).__inkcopyStoreForTests, null, { timeout: 30_000 })
    await win2.waitForTimeout(500)

    const restored = await win2.evaluate(() => {
      const s = (window as any).__inkcopyStoreForTests.getState()
      return { promptCount: s.promptFiles.length, chapterCount: s.chapterFiles.length, concurrent: s.concurrentChapters }
    })
    // Folder lists empty (folder gone) but other settings restored.
    expect(restored.promptCount).toBe(0)
    expect(restored.chapterCount).toBe(0)
    expect(restored.concurrent).toBe(7)
    await app2.close()
  })
})
