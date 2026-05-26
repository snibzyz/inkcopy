import { useEffect, useState } from 'react'
import { useStore } from './state/store'
import { buildPastePayload, writePayloadToClipboard } from './lib/paste'
import { hydrateFromSettings, startAutosave } from './lib/persistence'
import { TitleBar } from './components/TitleBar'
import { MinimizedStatus } from './components/MinimizedStatus'
import { ModeToggle } from './components/ModeToggle'
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
    const offPaste = window.inkcopy?.hotkey?.onPaste?.(() => {
      void (async () => {
        const state = useStore.getState()
        const payload = await buildPastePayload(state)
        if (!payload) return
        try {
          const kind = await writePayloadToClipboard(payload)
          await window.inkcopy.log.info('paste', 'wrote clipboard', {
            kind,
            chars: payload.text.length,
            files: payload.files.length,
            label: payload.toastLabel,
          })
        } catch (err) {
          showToast({ message: `เขียน clipboard ไม่ได้: ${(err as Error).message}`, tone: 'error', durationMs: 4000 })
          return
        }
        showToast({
          message: `วาง: ${state.promptFiles.length} Prompt + ${payload.toastLabel}`,
          tone: 'paste',
          durationMs: 1800,
        })
        advanceChapter(payload.chapterCount)
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
  }, [advanceChapter, concurrent, setCurrentIndex, showToast, togglePaused])

  // Detect available update once at boot
  useEffect(() => {
    const off = window.inkcopy?.app?.onUpdateAvailable?.((info) => {
      useStore.getState().setUpdate(info)
    })
    return () => off?.()
  }, [])

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
        <main className="flex flex-1 flex-col gap-2.5 overflow-y-auto p-3" data-testid="content">
          <ModeToggle />
          <StatusBar />
          <DiagnosticsRow />

          {mode === 'paste' ? (
            <>
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
