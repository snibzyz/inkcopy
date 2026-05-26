import { useEffect, useState } from 'react'
import { useStore } from '../state/store'
import { Codicon } from '../ui/Codicon'
import { cn } from '../ui/cn'

/**
 * Quick "all → text / all → file" toggle bar shown above PromptSection.
 *
 * Why this exists: on Windows, Chrome's textarea ignores CF_HDROP file
 * pastes via Ctrl+V — files only attach when dropped, not pasted. macOS
 * is the opposite: NSPasteboard public.file-url IS recognised by Chrome
 * on Cmd+V (which is why the same workflow works there). Without a quick
 * way to flip every prompt + chapter mode at once, Windows users have to
 * click each row individually after picking a folder of N files.
 */
export function QuickToggleBar() {
  const promptFiles = useStore((s) => s.promptFiles)
  const promptPasteModes = useStore((s) => s.promptPasteModes)
  const chapterPasteAsText = useStore((s) => s.chapterPasteAsText)
  const setAllPasteModes = useStore((s) => s.setAllPasteModes)
  const [isWin, setIsWin] = useState(false)

  useEffect(() => {
    setIsWin(!!window.inkcopy?.isWin)
  }, [])

  // Resolve current bulk-state: all-text, all-file, or mixed.
  const allText =
    chapterPasteAsText &&
    promptFiles.length > 0 &&
    promptFiles.every((f) => promptPasteModes[f.displayName] === true)
  const allFile =
    !chapterPasteAsText &&
    promptFiles.every((f) => (promptPasteModes[f.displayName] ?? false) === false)

  return (
    <div className="flex items-center gap-2 rounded-sm border border-vscode-border bg-vscode-input/30 px-2.5 py-1.5 text-[12px]">
      <Codicon name="settings-gear" size={11} className="text-vscode-muted" />
      <span className="text-vscode-muted">วางแบบเดียวกันหมด:</span>
      <div className="flex overflow-hidden rounded-sm border border-vscode-border">
        <button
          type="button"
          onClick={() => setAllPasteModes(true)}
          className={cn(
            'h-7 px-3 text-[12px]',
            allText
              ? 'bg-vscode-brand/15 text-vscode-brand font-semibold'
              : 'bg-vscode-button text-vscode-fg hover:bg-vscode-list-hover',
          )}
          title="อ่านเนื้อหาไฟล์ทั้งหมด แล้ววางเป็นข้อความ (ทำงานทุก browser / OS)"
          data-testid="bulk-all-text"
        >
          ข้อความทั้งหมด
        </button>
        <button
          type="button"
          onClick={() => setAllPasteModes(false)}
          className={cn(
            'h-7 px-3 text-[12px]',
            allFile
              ? 'bg-vscode-brand/15 text-vscode-brand font-semibold'
              : 'bg-vscode-button text-vscode-fg hover:bg-vscode-list-hover',
          )}
          title="แนบเป็นไฟล์ (file URL) — macOS: ใช้กับ Gemini/ChatGPT ได้ · Windows: ใช้ได้เฉพาะ drag-drop ไม่ใช่ Ctrl+V"
          data-testid="bulk-all-file"
        >
          ไฟล์ทั้งหมด
        </button>
      </div>
      {isWin && allFile ? (
        <span className="ml-auto flex items-center gap-1 text-[11px] text-yellow-300" data-testid="windows-file-hint">
          <Codicon name="warning" size={11} />
          <span>Windows: Ctrl+V ในแชทบนเว็บมักไม่รับไฟล์ — ลอง "ข้อความทั้งหมด"</span>
        </span>
      ) : null}
    </div>
  )
}
