import { useStore } from '../state/store'
import { Codicon } from '../ui/Codicon'
import { cn } from '../ui/cn'

export function ActionRow() {
  const paused = useStore((s) => s.paused)
  const hotkeysRegistered = useStore((s) => s.hotkeysRegistered)
  const promptFiles = useStore((s) => s.promptFiles)
  const chapterFiles = useStore((s) => s.chapterFiles)
  const togglePaused = useStore((s) => s.togglePaused)
  const setHotkeysRegistered = useStore((s) => s.setHotkeysRegistered)
  const showToast = useStore((s) => s.showToast)

  const canRegister = promptFiles.length > 0 && chapterFiles.length > 0

  const registerHotkeys = async () => {
    if (!canRegister) return
    try {
      const res = await window.inkcopy.hotkey.register()
      setHotkeysRegistered(res.ok)
      if (res.ok) {
        showToast({ message: 'Hotkey ลงทะเบียนแล้ว — Cmd/Ctrl+V พร้อมใช้', tone: 'info', durationMs: 2500 })
      } else {
        showToast({ message: `ลงทะเบียน hotkey ไม่ได้: ${res.reason ?? 'unknown'}`, tone: 'error', durationMs: 4000 })
      }
    } catch (err) {
      showToast({ message: `Error: ${(err as Error).message}`, tone: 'error', durationMs: 4000 })
    }
  }

  const unregisterHotkeys = async () => {
    await window.inkcopy.hotkey.unregister()
    setHotkeysRegistered(false)
    showToast({ message: 'Hotkey หยุดทำงานแล้ว', tone: 'info', durationMs: 2000 })
  }

  return (
    <div className="flex items-center gap-1.5">
      {!hotkeysRegistered ? (
        <button
          type="button"
          onClick={registerHotkeys}
          disabled={!canRegister}
          className={cn(
            'flex h-8 items-center gap-1.5 rounded-sm px-3 text-[13px] font-semibold',
            canRegister
              ? 'bg-vscode-brand text-vscode-titlebar hover:brightness-110'
              : 'cursor-not-allowed bg-vscode-input text-vscode-muted',
          )}
          data-testid="register-hotkey"
        >
          <Codicon name="play" size={12} />
          <span>เริ่มใช้งาน Hotkey</span>
        </button>
      ) : (
        <button
          type="button"
          onClick={unregisterHotkeys}
          className="flex h-8 items-center gap-1.5 rounded-sm border border-vscode-border bg-vscode-button px-3 text-[13px] text-vscode-fg hover:bg-vscode-list-hover"
          data-testid="unregister-hotkey"
        >
          <Codicon name="debug-stop" size={12} />
          <span>หยุด Hotkey</span>
        </button>
      )}

      <button
        type="button"
        onClick={togglePaused}
        disabled={!hotkeysRegistered}
        className={cn(
          'flex h-8 items-center gap-1.5 rounded-sm border border-vscode-border px-3 text-[13px]',
          paused
            ? 'bg-yellow-500/20 text-yellow-300'
            : hotkeysRegistered
              ? 'bg-vscode-button text-vscode-fg hover:bg-vscode-list-hover'
              : 'cursor-not-allowed bg-vscode-input text-vscode-muted',
        )}
        data-testid="pause-toggle"
        title="กด F12 ก็ได้"
      >
        <Codicon name={paused ? 'play' : 'debug-pause'} size={12} />
        <span>{paused ? 'ใช้งานต่อ' : 'หยุดชั่วคราว'}</span>
      </button>

      <div className="ml-auto flex items-center gap-2 text-[13px] text-vscode-muted">
        <span className="flex items-center gap-1">
          <kbd className="rounded-sm border border-vscode-border bg-vscode-input px-1.5 py-0.5 font-mono text-[10px]">F9</kbd>
          <span>prev</span>
        </span>
        <span className="flex items-center gap-1">
          <kbd className="rounded-sm border border-vscode-border bg-vscode-input px-1.5 py-0.5 font-mono text-[10px]">F10</kbd>
          <span>next</span>
        </span>
        <span className="flex items-center gap-1">
          <kbd className="rounded-sm border border-vscode-border bg-vscode-input px-1.5 py-0.5 font-mono text-[10px]">F12</kbd>
          <span>pause</span>
        </span>
      </div>
    </div>
  )
}
