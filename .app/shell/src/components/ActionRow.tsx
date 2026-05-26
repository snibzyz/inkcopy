import { useStore } from '../state/store'
import { Codicon } from '../ui/Codicon'
import { cn } from '../ui/cn'

/**
 * Footer row — pause toggle + manual prev/next + keyboard hints.
 * App.tsx auto-registers the hotkey listener when both folders are picked,
 * so there's no "register" button. The prev/next buttons are user-visible
 * equivalents of F9/F10 for people who'd rather click than learn keys.
 */
export function ActionRow() {
  const paused = useStore((s) => s.paused)
  const hotkeysRegistered = useStore((s) => s.hotkeysRegistered)
  const togglePaused = useStore((s) => s.togglePaused)
  const concurrent = useStore((s) => s.concurrentChapters)
  const currentIndex = useStore((s) => s.currentIndex)
  const chapterCount = useStore((s) => s.chapterFiles.length)
  const setCurrentIndex = useStore((s) => s.setCurrentIndex)

  const canGoPrev = currentIndex > 0
  const canGoNext = currentIndex < chapterCount

  const goPrev = () => setCurrentIndex(Math.max(0, currentIndex - concurrent))
  const goNext = () => setCurrentIndex(Math.min(chapterCount, currentIndex + concurrent))

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={togglePaused}
        disabled={!hotkeysRegistered}
        className={cn(
          'flex h-8 items-center gap-1.5 rounded-sm border border-vscode-border px-3 text-[13px]',
          paused
            ? 'bg-yellow-500/20 text-yellow-300'
            : hotkeysRegistered
              ? 'bg-vscode-brand text-vscode-titlebar font-semibold hover:brightness-110'
              : 'cursor-not-allowed bg-vscode-input text-vscode-muted',
        )}
        data-testid="pause-toggle"
        title="กด F12 ก็ได้"
      >
        <Codicon name={paused ? 'play' : 'debug-pause'} size={12} />
        <span>{paused ? 'ใช้งานต่อ' : hotkeysRegistered ? 'หยุดชั่วคราว' : 'รอเลือกโฟลเดอร์'}</span>
      </button>

      <div className="flex overflow-hidden rounded-sm border border-vscode-border">
        <button
          type="button"
          onClick={goPrev}
          disabled={!canGoPrev}
          className={cn(
            'flex h-8 items-center gap-1 px-2.5 text-[13px]',
            canGoPrev ? 'bg-vscode-button text-vscode-fg hover:bg-vscode-list-hover' : 'cursor-not-allowed bg-vscode-input text-vscode-muted',
          )}
          title={`ตอนก่อนหน้า (F9) · ถอย ${concurrent} ตอน`}
          data-testid="prev-btn"
        >
          <Codicon name="chevron-left" size={12} />
          <span>ก่อน</span>
        </button>
        <button
          type="button"
          onClick={goNext}
          disabled={!canGoNext}
          className={cn(
            'flex h-8 items-center gap-1 border-l border-vscode-border px-2.5 text-[13px]',
            canGoNext ? 'bg-vscode-button text-vscode-fg hover:bg-vscode-list-hover' : 'cursor-not-allowed bg-vscode-input text-vscode-muted',
          )}
          title={`ตอนถัดไป (F10) · ข้าม ${concurrent} ตอน`}
          data-testid="next-btn"
        >
          <span>ถัดไป</span>
          <Codicon name="chevron-right" size={12} />
        </button>
      </div>

      <div className="ml-auto flex items-center gap-2 text-[13px] text-vscode-muted">
        <span className="flex items-center gap-1">
          <kbd className="rounded-sm border border-vscode-border bg-vscode-input px-1.5 py-0.5 font-mono text-[10px]">F9</kbd>
          <kbd className="rounded-sm border border-vscode-border bg-vscode-input px-1.5 py-0.5 font-mono text-[10px]">F10</kbd>
          <span>ก่อน/ถัด</span>
        </span>
        <span className="flex items-center gap-1">
          <kbd className="rounded-sm border border-vscode-border bg-vscode-input px-1.5 py-0.5 font-mono text-[10px]">F12</kbd>
          <span>หยุด</span>
        </span>
      </div>
    </div>
  )
}
