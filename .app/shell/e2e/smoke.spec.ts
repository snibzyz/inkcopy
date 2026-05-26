import { test, expect } from './fixtures/electron'

test.describe('INKCOPY — smoke', () => {
  test('window opens with title bar + frameless chrome', async ({ window }) => {
    await expect(window.locator('text=INKCOPY').first()).toBeVisible()
    await expect(window.getByTestId('status-bar')).toBeVisible()
  })

  test('starts in PASTE mode with prompt + chapter empty', async ({ window }) => {
    const pasteBtn = window.getByTestId('mode-paste')
    await expect(pasteBtn).toHaveAttribute('data-active', 'true')
    await expect(window.getByTestId('prompt-section')).toBeVisible()
    await expect(window.getByTestId('chapter-section')).toBeVisible()
    await expect(window.getByTestId('status-bar')).toContainText('เลือกโฟลเดอร์ Prompt + ตอนก่อน')
  })

  test('mode toggle: PASTE → COPY shows Output section', async ({ window }) => {
    await window.getByTestId('mode-copy').click()
    await expect(window.getByTestId('mode-copy')).toHaveAttribute('data-active', 'true')
    await expect(window.getByTestId('output-section')).toBeVisible()
    // PromptSection should disappear (COPY doesn't use prompts)
    await expect(window.getByTestId('prompt-section')).toHaveCount(0)
  })

  test('mode toggle: COPY → VOCAB shows vocab filename input', async ({ window }) => {
    await window.getByTestId('mode-copy').click()
    await window.getByTestId('mode-vocab').click()
    await expect(window.getByTestId('mode-vocab')).toHaveAttribute('data-active', 'true')
    await expect(window.getByTestId('vocab-section')).toBeVisible()
    await expect(window.getByTestId('vocab-filename')).toHaveValue('vocab.txt')
  })

  test('vocab filename can be changed', async ({ window }) => {
    await window.getByTestId('mode-vocab').click()
    const input = window.getByTestId('vocab-filename')
    await input.fill('mywords.txt')
    await expect(input).toHaveValue('mywords.txt')
  })

  test('diagnostics shows hotkey not registered initially', async ({ window }) => {
    const diag = window.locator('[data-testid="diag-bit-muted"]')
    await expect(diag).toContainText('ยังไม่พร้อมใช้')
  })

  test('concurrent chapters input clamps to 1-20', async ({ window }) => {
    const input = window.getByTestId('concurrent-input')
    await input.fill('25')
    await input.blur()
    await expect(input).toHaveValue('20')
    await input.fill('0')
    await input.blur()
    await expect(input).toHaveValue('1')
  })

  test('pause toggle disabled until hotkeys registered', async ({ window }) => {
    await expect(window.getByTestId('pause-toggle')).toBeDisabled()
  })

  test('register hotkey button disabled when no prompt/chapter set', async ({ window }) => {
    await expect(window.getByTestId('register-hotkey')).toBeDisabled()
  })
})

test.describe('INKCOPY — hotkey simulation via E2E hook', () => {
  test('seed state then fire paste hotkey advances chapter index', async ({ window }) => {
    // Seed the renderer store directly so we don't need real folder pickers.
    await window.evaluate(() => {
      const store = (window as any).__inkcopyStoreForTests
      if (!store) throw new Error('test store hook missing — expose useStore on window for E2E')
      store.getState().setPromptFolder('/tmp/p', [
        { displayName: 'p1.txt', path: '/tmp/p/p1.txt' },
      ])
      store.getState().setChapterFolder('/tmp/c', [
        { displayName: 'ch001.txt', path: '/tmp/c/ch001.txt', detectedNumber: 1 },
        { displayName: 'ch002.txt', path: '/tmp/c/ch002.txt', detectedNumber: 2 },
        { displayName: 'ch003.txt', path: '/tmp/c/ch003.txt', detectedNumber: 3 },
      ])
      store.getState().setHotkeysRegistered(true)
    })

    await expect(window.getByTestId('status-bar')).toContainText('1/3')

    // Fire a paste via the renderer test hook (preload exposes _testFirePaste
    // when INKCOPY_E2E=1). This dispatches 'hotkey:paste' → onPaste subscribers
    // in App.tsx → advanceChapter(1).
    await window.evaluate(async () => {
      await (window as any).inkcopy.hotkey['_testFirePaste']()
    })

    await expect(window.getByTestId('status-bar')).toContainText('2/3')
  })

  test('fire next hotkey moves chapter index forward', async ({ window }) => {
    await window.evaluate(() => {
      const store = (window as any).__inkcopyStoreForTests
      store.getState().setPromptFolder('/tmp/p', [{ displayName: 'p.txt', path: '/tmp/p/p.txt' }])
      store.getState().setChapterFolder('/tmp/c', [
        { displayName: 'ch1.txt', path: '/tmp/c/ch1.txt', detectedNumber: 1 },
        { displayName: 'ch2.txt', path: '/tmp/c/ch2.txt', detectedNumber: 2 },
      ])
      store.getState().setHotkeysRegistered(true)
    })
    await expect(window.getByTestId('status-bar')).toContainText('1/2')
    await window.evaluate(async () => {
      await (window as any).inkcopy.hotkey['_testFireNext']?.()
    })
    await expect(window.getByTestId('status-bar')).toContainText('2/2')
  })

  test('toast appears when paste hotkey fires', async ({ window }) => {
    await window.evaluate(() => {
      const store = (window as any).__inkcopyStoreForTests
      store.getState().setPromptFolder('/tmp/p', [{ displayName: 'p.txt', path: '/tmp/p/p.txt' }])
      store.getState().setChapterFolder('/tmp/c', [
        { displayName: 'ch1.txt', path: '/tmp/c/ch1.txt', detectedNumber: 1 },
      ])
      store.getState().setHotkeysRegistered(true)
    })
    await window.evaluate(async () => {
      await (window as any).inkcopy.hotkey['_testFirePaste']?.()
    })
    await expect(window.locator('[data-testid="toast"][data-tone="paste"]')).toBeVisible()
  })
})

test.describe('INKCOPY — chapter detection (renderer-side lib)', () => {
  test('detectChapterNumber + naturalCompare exposed for verification', async ({ window }) => {
    const result = await window.evaluate(() => {
      const lib = (window as any).__inkcopyChaptersForTests
      if (!lib) return null
      return {
        seven: lib.detectChapterNumber('Episode_007.txt'),
        eleven: lib.detectChapterNumber('Title 011.txt'),
        none: lib.detectChapterNumber('intro.txt'),
        sort: ['ch10.txt', 'ch2.txt', 'ch1.txt'].sort(lib.naturalCompare),
      }
    })
    expect(result).not.toBeNull()
    expect(result!.seven).toBe(7)
    expect(result!.eleven).toBe(11)
    expect(result!.none).toBeNull()
    expect(result!.sort).toEqual(['ch1.txt', 'ch2.txt', 'ch10.txt'])
  })
})
