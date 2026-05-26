import { test, expect } from './fixtures/electron'
import path from 'node:path'

const SAMPLE_PROMPTS = path.resolve(__dirname, 'fixtures', 'sample-data', 'prompts')
const SAMPLE_CHAPTERS = path.resolve(__dirname, 'fixtures', 'sample-data', 'chapters')

test.describe('INKCOPY — load real folders via fs IPC', () => {
  test('listing the sample prompts folder returns 2 files in natural order', async ({ window }) => {
    const entries = await window.evaluate(async (dir: string) => {
      return (window as any).inkcopy.fs.listDir(dir, { recursive: false })
    }, SAMPLE_PROMPTS)
    expect(entries).toHaveLength(2)
    const names = entries.map((e: { name: string }) => e.name).sort()
    expect(names).toContain('glossary.txt')
    expect(names).toContain('system-prompt.txt')
  })

  test('listing chapters yields 4 entries with detectable chapter numbers', async ({ window }) => {
    const result = await window.evaluate(async (dir: string) => {
      const entries: { name: string }[] = await (window as any).inkcopy.fs.listDir(dir, { recursive: false })
      const lib = (window as any).__inkcopyChaptersForTests
      return entries
        .map((e) => ({ name: e.name, detected: lib.detectChapterNumber(e.name) }))
        .sort((a, b) => lib.naturalCompare(a.name, b.name))
    }, SAMPLE_CHAPTERS)
    expect(result).toEqual([
      { name: 'chapter0001.txt', detected: 1 },
      { name: 'chapter0002.txt', detected: 2 },
      { name: 'chapter0003.txt', detected: 3 },
      { name: 'chapter0004.txt', detected: 4 },
    ])
  })

  test('reading chapter content via fs.readText returns the Thai novel snippet', async ({ window }) => {
    const text = await window.evaluate(async (file: string) => {
      return (window as any).inkcopy.fs.readText(file)
    }, path.join(SAMPLE_CHAPTERS, 'chapter0001.txt'))
    expect(text).toContain('บทที่ ๑')
    expect(text).toContain('เยว่เฉิน')
    expect(text).toContain('ง้าวมังกรมาร')
  })

  test('seed store with real chapter paths → status bar shows count', async ({ window }) => {
    await window.evaluate(async ({ promptDir, chapterDir }: { promptDir: string; chapterDir: string }) => {
      const store = (window as any).__inkcopyStoreForTests
      const lib = (window as any).__inkcopyChaptersForTests
      const inkcopy = (window as any).inkcopy

      const promptEntries: { name: string; path: string; isFile: boolean }[] = await inkcopy.fs.listDir(promptDir, { recursive: false })
      const promptFiles = promptEntries
        .filter((e) => e.isFile)
        .sort((a, b) => lib.naturalCompare(a.name, b.name))
        .map((e) => ({ displayName: e.name, path: e.path }))
      store.getState().setPromptFolder(promptDir, promptFiles)

      const chEntries: { name: string; path: string; isFile: boolean }[] = await inkcopy.fs.listDir(chapterDir, { recursive: false })
      const chapterFiles = chEntries
        .filter((e) => e.isFile)
        .sort((a, b) => lib.naturalCompare(a.name, b.name))
        .map((e) => ({ displayName: e.name, path: e.path, detectedNumber: lib.detectChapterNumber(e.name) }))
      store.getState().setChapterFolder(chapterDir, chapterFiles)
    }, { promptDir: SAMPLE_PROMPTS, chapterDir: SAMPLE_CHAPTERS })

    await expect(window.getByTestId('status-bar')).toContainText('1/4')
    await expect(window.getByTestId('chapter-count')).toContainText('4 / 4 ตอน')
    await expect(window.locator('[data-testid="chapter-row"]')).toHaveCount(4)
  })

  test('range filter 2..3 shrinks visible chapters and resets index', async ({ window }) => {
    await window.evaluate(async ({ chapterDir }: { chapterDir: string }) => {
      const store = (window as any).__inkcopyStoreForTests
      const lib = (window as any).__inkcopyChaptersForTests
      const inkcopy = (window as any).inkcopy
      const entries: { name: string; path: string; isFile: boolean }[] = await inkcopy.fs.listDir(chapterDir, { recursive: false })
      const chapterFiles = entries
        .filter((e) => e.isFile)
        .sort((a, b) => lib.naturalCompare(a.name, b.name))
        .map((e) => ({ displayName: e.name, path: e.path, detectedNumber: lib.detectChapterNumber(e.name) }))
      store.getState().setChapterFolder(chapterDir, chapterFiles)
      store.getState().setChapterRange({ lo: 2, hi: 3 })
    }, { chapterDir: SAMPLE_CHAPTERS })

    await expect(window.getByTestId('chapter-count')).toContainText('2 / 4 ตอน')
    await expect(window.locator('[data-testid="chapter-row"]')).toHaveCount(2)
  })
})

test.describe('INKCOPY — minimize/restore window', () => {
  test('clicking minimize shows current chapter in title bar', async ({ window }) => {
    await window.evaluate(async ({ chapterDir }: { chapterDir: string }) => {
      const store = (window as any).__inkcopyStoreForTests
      const lib = (window as any).__inkcopyChaptersForTests
      const inkcopy = (window as any).inkcopy
      const entries: { name: string; path: string; isFile: boolean }[] = await inkcopy.fs.listDir(chapterDir, { recursive: false })
      const chapterFiles = entries
        .filter((e) => e.isFile)
        .sort((a, b) => lib.naturalCompare(a.name, b.name))
        .map((e) => ({ displayName: e.name, path: e.path, detectedNumber: lib.detectChapterNumber(e.name) }))
      store.getState().setChapterFolder(chapterDir, chapterFiles)
    }, { chapterDir: SAMPLE_CHAPTERS })

    // Content visible before minimize
    await expect(window.getByTestId('content')).toBeVisible()

    await window.getByTestId('minimize-toggle').click()
    await expect(window.getByTestId('content')).toHaveCount(0)
    await expect(window.getByTestId('titlebar-current')).toBeVisible()
    await expect(window.getByTestId('titlebar-current')).toContainText('chapter0001')
    await expect(window.getByTestId('titlebar-current')).toContainText('1/4')
  })

  test('restoring the window brings back full content', async ({ window }) => {
    await window.getByTestId('minimize-toggle').click()
    await expect(window.getByTestId('content')).toHaveCount(0)
    await window.getByTestId('minimize-toggle').click()
    await expect(window.getByTestId('content')).toBeVisible()
  })
})
