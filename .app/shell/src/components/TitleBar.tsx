import { useEffect, useState } from 'react'
import { useStore } from '../state/store'
import { Codicon } from '../ui/Codicon'

const FULL_HEIGHT = 820
// 36px title bar + 56px MinimizedStatus row + a little breathing room.
const COLLAPSED_HEIGHT = 100

/**
 * Frameless-window title bar — drag region on the whole bar; controls are
 * marked `no-drag` so they stay clickable. When minimized we resize the
 * native window down (so it really becomes a tiny overlay rather than just
 * hiding content) and show the current chapter inline so the user always
 * knows where they are without expanding.
 */
export function TitleBar() {
  const update = useStore((s) => s.update)
  const minimized = useStore((s) => s.minimized)
  const toggleMinimized = useStore((s) => s.toggleMinimized)
  const [version, setVersion] = useState<string>('')

  useEffect(() => {
    setVersion(window.inkcopy?.app?.version ?? '')
  }, [])

  // Sync renderer minimized state → native BrowserWindow height so the
  // overlay actually shrinks (not just hides content).
  useEffect(() => {
    window.inkcopy?.window?.setHeight?.(minimized ? COLLAPSED_HEIGHT : FULL_HEIGHT)
  }, [minimized])

  return (
    <div
      className="flex h-9 items-center border-b border-vscode-border bg-vscode-titlebar px-3 text-[13px] select-none"
      style={{ WebkitAppRegion: 'drag' } as React.CSSProperties}
    >
      <Codicon name="clippy" className="text-vscode-brand" />
      <span className="ml-2 font-semibold tracking-[0.04em] text-vscode-fg-bright">INKCOPY</span>
      {version ? <span className="ml-1.5 text-[13px] text-vscode-muted">v{version}</span> : null}

      <div
        className="ml-auto flex items-center gap-1"
        style={{ WebkitAppRegion: 'no-drag' } as React.CSSProperties}
      >
        {update.available && update.tag ? (
          <button
            type="button"
            onClick={() => window.inkcopy?.app?.applyUpdate()}
            className="flex h-6 items-center gap-1 rounded-sm bg-vscode-brand/20 px-2 text-[13px] text-vscode-brand hover:bg-vscode-brand/30"
            title={`อัปเดต ${update.tag} พร้อมติดตั้ง — คลิกเพื่อติดตั้ง`}
            data-testid="update-btn"
          >
            <Codicon name="cloud-download" size={12} />
            <span>{update.tag}</span>
          </button>
        ) : null}

        <button
          type="button"
          onClick={toggleMinimized}
          className="flex h-6 w-6 items-center justify-center rounded-sm text-vscode-fg hover:bg-vscode-list-hover"
          title={minimized ? 'ขยายหน้าต่าง' : 'ย่อให้เล็ก (ยังเห็นชื่อตอนปัจจุบัน)'}
          data-testid="minimize-toggle"
        >
          <Codicon name={minimized ? 'chevron-down' : 'chevron-up'} size={14} />
        </button>

        <button
          type="button"
          onClick={() => window.inkcopy?.window?.minimize()}
          className="flex h-6 w-6 items-center justify-center rounded-sm text-vscode-fg hover:bg-vscode-list-hover"
          title="ซ่อนไป Taskbar / Dock"
          data-testid="taskbar-min"
        >
          <Codicon name="chrome-minimize" size={12} />
        </button>

        <button
          type="button"
          onClick={() => window.inkcopy?.window?.close()}
          className="flex h-6 w-6 items-center justify-center rounded-sm text-vscode-fg hover:bg-red-500/20 hover:text-red-300"
          title="ปิด INKCOPY"
          data-testid="close-btn"
        >
          <Codicon name="chrome-close" size={12} />
        </button>
      </div>
    </div>
  )
}
