import { useStore } from '../state/store'
import { Codicon } from '../ui/Codicon'
import { cn } from '../ui/cn'

const MODE_LABEL: Record<string, string> = {
  paste: 'วาง',
  copy: 'คัดลอก',
  vocab: 'ศัพท์',
}

function trimStem(name: string): string {
  return name.replace(/\.[^.]+$/, '')
}

/**
 * Compact status panel shown when the overlay is collapsed. Mirrors the
 * Python tray hint: at a glance the user must see (1) what mode, (2) which
 * prompt-set is loaded, (3) which chapter is queued, (4) how many remain.
 * Without this the minimized window is just an empty strip — Python users
 * complained the Electron port "ย่อแล้วเล็กมาก ไม่บอกอะไรเลย".
 */
export function MinimizedStatus() {
  const mode = useStore((s) => s.mode)
  const paused = useStore((s) => s.paused)
  const hotkeysRegistered = useStore((s) => s.hotkeysRegistered)
  const promptFiles = useStore((s) => s.promptFiles)
  const chapterFiles = useStore((s) => s.chapterFiles)
  const currentIndex = useStore((s) => s.currentIndex)
  const concurrent = useStore((s) => s.concurrentChapters)
  const togglePaused = useStore((s) => s.togglePaused)

  const total = chapterFiles.length
  const remaining = Math.max(0, total - currentIndex)
  const toPaste = Math.min(concurrent, remaining)
  const current = currentIndex < total ? chapterFiles[currentIndex] : null
  const last = toPaste > 1 ? chapterFiles[currentIndex + toPaste - 1] : null
  const progress = total > 0 ? Math.round((currentIndex / total) * 100) : 0

  const modeLabel = paused ? 'หยุดชั่วคราว' : MODE_LABEL[mode] ?? mode
  const modeTone = paused
    ? 'bg-yellow-500/20 text-yellow-300'
    : hotkeysRegistered
      ? 'bg-vscode-brand/20 text-vscode-brand'
      : 'bg-vscode-input text-vscode-muted'

  return (
    <div
      className="flex items-center gap-2 border-b border-vscode-border bg-vscode-titlebar/80 px-3 py-1.5"
      data-testid="minimized-status"
    >
      <span className={cn('shrink-0 rounded-sm px-2 py-0.5 text-[11px] font-semibold tracking-[0.04em]', modeTone)}>
        {modeLabel.toUpperCase()}
      </span>

      <div className="flex min-w-0 flex-1 flex-col gap-0.5 text-[12px]">
        {current ? (
          <>
            <div className="flex items-center gap-1.5">
              <Codicon name="files" size={11} className="shrink-0 text-vscode-muted" />
              <span className="shrink-0 text-vscode-muted">{promptFiles.length} prompt +</span>
              <span className="truncate font-semibold text-vscode-fg-bright" title={current.path}>
                {last
                  ? `${trimStem(current.displayName)} … ${trimStem(last.displayName)}`
                  : trimStem(current.displayName)}
              </span>
            </div>
            <div className="flex items-center gap-1.5 text-[11px] text-vscode-muted">
              <span>
                ตอนที่ {currentIndex + 1}
                {toPaste > 1 ? `–${currentIndex + toPaste}` : ''} / {total}
              </span>
              <span className="text-vscode-border">·</span>
              <span>เหลือ {remaining} ตอน</span>
              {hotkeysRegistered && !paused ? (
                <>
                  <span className="text-vscode-border">·</span>
                  <span className="flex items-center gap-1 text-vscode-success">
                    <Codicon name="pulse" size={9} />
                    พร้อมรับ Cmd+V
                  </span>
                </>
              ) : null}
            </div>
          </>
        ) : (
          <div className="text-[12px] text-vscode-muted">
            {chapterFiles.length === 0 ? 'ยังไม่ได้เลือกตอน' : 'วางครบทุกตอนแล้ว'}
          </div>
        )}
      </div>

      {hotkeysRegistered ? (
        <button
          type="button"
          onClick={togglePaused}
          className={cn(
            'flex h-7 shrink-0 items-center gap-1 rounded-sm border border-vscode-border px-2 text-[11px]',
            paused
              ? 'bg-yellow-500/20 text-yellow-300'
              : 'bg-vscode-button text-vscode-fg hover:bg-vscode-list-hover',
          )}
          title={paused ? 'ใช้งานต่อ (F12)' : 'หยุดชั่วคราว (F12)'}
          data-testid="minimized-pause"
        >
          <Codicon name={paused ? 'play' : 'debug-pause'} size={11} />
          <span>{paused ? 'ต่อ' : 'หยุด'}</span>
        </button>
      ) : null}

      {total > 0 ? (
        <div className="h-1 w-16 shrink-0 overflow-hidden rounded-full bg-vscode-input">
          <div
            className="h-full bg-vscode-brand transition-[width] duration-300"
            style={{ width: `${progress}%` }}
            data-testid="minimized-progress"
          />
        </div>
      ) : null}
    </div>
  )
}
