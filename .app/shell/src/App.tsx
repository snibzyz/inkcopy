import { useEffect, useState } from 'react'
import { useStore } from './state/store'
import { buildPastePayload, writePayloadToClipboard } from './lib/paste'
import { hydrateFromSettings, startAutosave } from './lib/persistence'
import { TitleBar } from './components/TitleBar'
import { MinimizedStatus } from './components/MinimizedStatus'
import { ModeToggle } from './components/ModeToggle'
import { QuickToggleBar } from './components/QuickToggleBar'
import { StatusBar } from './components/StatusBar'
import { DiagnosticsRow } from './components/DiagnosticsRow'
import { PromptSection } from './components/PromptSection'
import { ChapterSection } from './components/ChapterSection'
import { OutputSection } from './components/OutputSection'
import { ConcurrentRow } from './components/ConcurrentRow'
import { ActionRow } from './components/ActionRow'
import { ToastStack } from './components/ToastStack'

/**
 * INKCOPY overlay — port of SmartClipboardOverlay in inkcopy.py.
 *
 * Layout follows the Python window section-by-section:
 *   TitleBar → ModeToggle → StatusBar → DiagnosticsRow → [mode content]
 *     PASTE: Prompt + Chapter + Concurrent + Actions
 *     COPY : Chapter + Output + Concurrent + Actions
 *     VOCAB: vocab filename + Actions
 *
 * Hotkey events are wired here so the listener fires the right store action
 * regardless of which section currently has focus.
 */
export default function App() {
  const mode = useStore((s) => s.mode)
  const minimized = useStore((s) => s.minimized)
  const advanceChapter = useStore((s) => s.advanceChapter)
  const setCurrentIndex = useStore((s) => s.setCurrentIndex)
  const setStagedPendingFilePaths = useStore((s) => s.setStagedPendingFilePaths)
  const setStagedSequenceActive = useStore((s) => s.setStagedSequenceActive)
  const togglePaused = useStore((s) => s.togglePaused)
  const concurrent = useStore((s) => s.concurrentChapters)
  const showToast = useStore((s) => s.showToast)
  const [hydrated, setHydrated] = useState(false)

  // Hydrate persisted settings before any other effect kicks in. Autosave
  // starts AFTER hydration so the initial restore doesn't trigger a redundant
  // patch back to disk.
  useEffect(() => {
    let unsub: (() => void) | undefined
    void (async () => {
      await hydrateFromSettings()
      setHydrated(true)
      unsub = startAutosave()
    })()
    return () => {
      unsub?.()
    }
  }, [])

  useEffect(() => {
    // Cmd/Ctrl+V handler — by the time uiohook fires we're already AFTER the
    // OS has consumed the keypress, so the clipboard write happens too late
    // for *this* paste. We rely on the pre-load effect below to keep the
    // clipboard armed with the upcoming chapter; the handler here just toasts
    // what was just pasted and advances the index (which re-triggers the
    // effect to pre-load the next chapter).
    const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))
    const finishAdvance = () => {
      const state = useStore.getState()
      if (state.paused || state.mode !== 'paste') return
      if (!state.chapterFiles.length || state.currentIndex >= state.chapterFiles.length) return
      const remaining = state.chapterFiles.length - state.currentIndex
      const toPaste = Math.min(state.concurrentChapters, remaining)
      const first = state.chapterFiles[state.currentIndex]
      const last = toPaste > 1 ? state.chapterFiles[state.currentIndex + toPaste - 1] : null
      const trim = (n: string) => n.replace(/\.[^.]+$/, '')
      const label = last ? `${trim(first.displayName)} … ${trim(last.displayName)}` : trim(first.displayName)
      showToast({
        message: `วาง: ${state.promptFiles.length} Prompt + ${label}`,
        tone: 'paste',
        durationMs: 1800,
      })
      advanceChapter(toPaste)
    }

    const offPaste = window.inkcopy?.hotkey?.onPaste?.(() => {
      void (async () => {
        const state = useStore.getState()
        if (state.paused || state.mode !== 'paste') return
        if (state.stagedSequenceActive) return

        const stagedFiles = state.stagedPendingFilePaths?.slice() ?? []
        if (stagedFiles.length) {
          setStagedSequenceActive(true)
          setStagedPendingFilePaths(null)
          try {
            await sleep(Math.max(50, state.stagedMsAfterUserPaste))
            await window.inkcopy.clipboard.writeFiles(stagedFiles)
            await window.inkcopy.log.info('paste', 'staged files armed', { files: stagedFiles.length })
            await sleep(Math.max(40, state.stagedMsClipboardToCtrlV))
            const sent = await window.inkcopy.hotkey.sendPaste()
            if (!sent?.ok) {
              useStore.getState().showToast({
                message: 'ไฟล์อยู่ใน clipboard แล้ว กด Cmd/Ctrl+V อีกครั้งเพื่อวางไฟล์',
                tone: 'error',
                durationMs: 5000,
              })
              return
            }
            await sleep(Math.max(80, state.stagedMsAfterTextPaste))
            finishAdvance()
          } catch (err) {
            useStore.getState().showToast({
              message: `วางไฟล์อัตโนมัติไม่ได้: ${(err as Error).message}`,
              tone: 'error',
              durationMs: 5000,
            })
          } finally {
            setStagedSequenceActive(false)
          }
          return
        }

        finishAdvance()
      })()
    })
    const offPrev = window.inkcopy?.hotkey?.onPrev?.(() => {
      const { currentIndex } = useStore.getState()
      setCurrentIndex(Math.max(0, currentIndex - concurrent))
    })
    const offNext = window.inkcopy?.hotkey?.onNext?.(() => {
      const { currentIndex, chapterFiles } = useStore.getState()
      setCurrentIndex(Math.min(chapterFiles.length, currentIndex + concurrent))
    })
    const offPause = window.inkcopy?.hotkey?.onPause?.(() => {
      togglePaused()
    })
    return () => {
      offPaste?.()
      offPrev?.()
      offNext?.()
      offPause?.()
    }
  }, [
    advanceChapter,
    concurrent,
    setCurrentIndex,
    setStagedPendingFilePaths,
    setStagedSequenceActive,
    showToast,
    togglePaused,
  ])

  // Detect available update once at boot
  useEffect(() => {
    const off = window.inkcopy?.app?.onUpdateAvailable?.((info) => {
      useStore.getState().setUpdate(info)
    })
    return () => off?.()
  }, [])

  // Clipboard pre-load — keep the OS clipboard armed with the upcoming
  // chapter's payload so the user's Cmd+V pastes immediately. Mirrors
  // `_load_clipboard_paste_mode()` being called after every advance in
  // inkcopy.py. Without this, the renderer writes the clipboard AFTER the
  // user's Cmd+V was already consumed by the OS → user gets nothing.
  //
  // We subscribe once and write only when the relevant payload-shape fields
  // change (skipping cosmetic store updates like toast/diagnostics polls).
  useEffect(() => {
    if (!hydrated) return
    let cancelled = false
    let inFlight = false
    let pendingKey = ''
    let lastWritten = ''

    const fieldsKey = () => {
      const s = useStore.getState()
      return JSON.stringify({
        registered: s.hotkeysRegistered,
        paused: s.paused,
        mode: s.mode,
        ci: s.currentIndex,
        cc: s.concurrentChapters,
        cas: s.chapterPasteAsText,
        ip: s.includePrompt,
        ic: s.includeChapter,
        pp: s.promptPasteModes,
        pf: s.promptFiles.map((f) => f.path),
        cf: s.chapterFiles.map((f) => f.path),
      })
    }

    const writeIfNeeded = async () => {
      if (cancelled || inFlight) return
      const key = pendingKey || fieldsKey()
      pendingKey = ''
      if (key === lastWritten) return
      const state = useStore.getState()
      if (
        !state.hotkeysRegistered ||
        state.paused ||
        state.mode !== 'paste' ||
        !state.chapterFiles.length ||
        state.currentIndex >= state.chapterFiles.length
      ) {
        useStore.getState().setStagedPendingFilePaths(null)
        lastWritten = key
        return
      }
      inFlight = true
      try {
        const payload = await buildPastePayload(state)
        if (cancelled || !payload) return
        const written = await writePayloadToClipboard(payload)
        useStore.getState().setStagedPendingFilePaths(written.stagedFiles)
        lastWritten = key
        await window.inkcopy.log.info('paste', 'pre-loaded clipboard', {
          chars: payload.text.length,
          files: payload.files.length,
          kind: written.kind,
          label: payload.toastLabel,
        })
      } catch (err) {
        useStore.getState().showToast({
          message: `เตรียม clipboard ไม่ได้: ${(err as Error).message}`,
          tone: 'error',
          durationMs: 4000,
        })
      } finally {
        inFlight = false
        // Drain — handle any state changes that arrived while writing.
        if (!cancelled && pendingKey && pendingKey !== lastWritten) void writeIfNeeded()
      }
    }

    void writeIfNeeded()
    const unsub = useStore.subscribe(() => {
      const next = fieldsKey()
      if (next === lastWritten) return
      pendingKey = next
      if (!inFlight) void writeIfNeeded()
    })
    return () => {
      cancelled = true
      unsub()
    }
  }, [hydrated])

  // Auto-register / unregister hotkeys based on folder state — matches
  // inkcopy.py's behavior where the hotkey listener attaches as soon as both
  // folders are picked. Avoids forcing the user through an extra button click
  // every session.
  const promptCount = useStore((s) => s.promptFiles.length)
  const chapterCount = useStore((s) => s.chapterFiles.length)
  const hotkeysRegistered = useStore((s) => s.hotkeysRegistered)
  useEffect(() => {
    if (!hydrated) return
    const ready = promptCount > 0 && chapterCount > 0
    if (ready && !hotkeysRegistered) {
      void window.inkcopy?.hotkey?.register?.().then((res) => {
        useStore.getState().setHotkeysRegistered(!!res?.ok)
      })
    } else if (!ready && hotkeysRegistered) {
      void window.inkcopy?.hotkey?.unregister?.()
      useStore.getState().setHotkeysRegistered(false)
    }
  }, [hydrated, promptCount, chapterCount, hotkeysRegistered])

  return (
    <div className="flex h-screen flex-col overflow-hidden rounded-mac-sm border border-white/5 bg-vscode-editor/95 text-vscode-fg shadow-mac backdrop-blur-md">
      <TitleBar />

      {minimized ? (
        <MinimizedStatus />
      ) : (
        // overflow-hidden + min-h-0 are load-bearing: they bound the flex
        // children so ChapterSection's flex-1 list can become the actual
        // scroll container (otherwise the list grows past its border and
        // visually overlaps ConcurrentRow / ActionRow below it).
        <main className="flex flex-1 min-h-0 flex-col gap-2.5 overflow-hidden p-3" data-testid="content">
          <ModeToggle />
          <StatusBar />
          <DiagnosticsRow />

          {mode === 'paste' ? (
            <>
              <QuickToggleBar />
              <PromptSection />
              <ChapterSection />
              <ConcurrentRow />
            </>
          ) : null}

          {mode === 'copy' ? (
            <>
              <ChapterSection />
              <OutputSection />
              <ConcurrentRow />
            </>
          ) : null}

          {mode === 'vocab' ? <VocabSection /> : null}

          <ActionRow />
        </main>
      )}

      <ToastStack />
    </div>
  )
}

function VocabSection() {
  const vocabFilename = useStore((s) => s.vocabFilename)
  const vocabEntryCount = useStore((s) => s.vocabEntryCount)
  const setVocabFilename = useStore((s) => s.setVocabFilename)

  return (
    <section className="space-y-2" data-testid="vocab-section">
      <div className="flex items-center gap-2">
        <span className="text-[11px] uppercase tracking-[0.08em] text-vscode-muted">Vocab</span>
      </div>
      <div className="flex items-center gap-2 rounded-sm border border-vscode-border bg-vscode-input/30 px-2 py-1.5">
        <span className="text-[11px] text-vscode-muted">ไฟล์:</span>
        <input
          type="text"
          value={vocabFilename}
          onChange={(e) => setVocabFilename(e.target.value)}
          className="h-7 flex-1 rounded-sm border border-vscode-border bg-vscode-input px-2 text-[11px] text-vscode-fg outline-none focus:border-vscode-focus"
          data-testid="vocab-filename"
        />
        <span className="text-[11px] text-vscode-muted">entries: {vocabEntryCount}</span>
      </div>
      <p className="text-[11px] text-vscode-muted">
        ในโหมดนี้ INKCOPY ฟัง Clipboard — ทุกครั้งที่คุณ copy ข้อความใหม่ จะ append ไปยังไฟล์นี้พร้อมบรรทัดว่าง 2 บรรทัดคั่น
      </p>
    </section>
  )
}
