import { useStore } from '../state/store'
import type { PromptFile } from '../types/inkcopy'
import { Codicon } from '../ui/Codicon'
import { cn } from '../ui/cn'

interface Props {
  file: PromptFile
}

/**
 * Single prompt-file row with per-file paste-mode toggle: paste-as-text vs
 * paste-as-file-URL. Mirrors the prompt list rows in inkcopy.py
 * (prompt_paste_modes dict + per-row QButtonGroup).
 */
export function PromptFileRow({ file }: Props) {
  const asText = useStore((s) => s.promptPasteModes[file.displayName] ?? false)
  const setPromptPasteMode = useStore((s) => s.setPromptPasteMode)
  const removePromptFile = useStore((s) => s.removePromptFile)

  return (
    <div
      className="group flex items-center gap-2 rounded-sm border border-vscode-border bg-vscode-input/30 px-2 py-1 text-[13px]"
      data-testid="prompt-row"
    >
      <Codicon name={asText ? 'symbol-string' : 'file'} size={12} className="text-vscode-muted" />
      <span className="flex-1 truncate text-vscode-fg" title={file.path}>
        {file.displayName}
      </span>
      <div className="flex shrink-0 overflow-hidden rounded-sm border border-vscode-border">
        <button
          type="button"
          onClick={() => setPromptPasteMode(file.displayName, false)}
          className={cn(
            'h-6 px-2 text-[13px]',
            !asText ? 'bg-vscode-brand/15 text-vscode-brand' : 'text-vscode-muted hover:bg-vscode-list-hover',
          )}
          title="แนบเป็นไฟล์ (file URL)"
          data-testid="prompt-row-file"
        >
          ไฟล์
        </button>
        <button
          type="button"
          onClick={() => setPromptPasteMode(file.displayName, true)}
          className={cn(
            'h-6 px-2 text-[13px]',
            asText ? 'bg-vscode-brand/15 text-vscode-brand' : 'text-vscode-muted hover:bg-vscode-list-hover',
          )}
          title="วางเป็นข้อความ (อ่านเนื้อหาก่อน)"
          data-testid="prompt-row-text"
        >
          ข้อความ
        </button>
      </div>
      <button
        type="button"
        onClick={() => removePromptFile(file.path)}
        className="flex h-6 w-6 shrink-0 items-center justify-center rounded-sm text-vscode-muted opacity-60 hover:bg-red-500/15 hover:text-red-300 hover:opacity-100"
        title={`ลบ ${file.displayName} ออกจากรายการ`}
        data-testid="prompt-row-remove"
      >
        <Codicon name="close" size={11} />
      </button>
    </div>
  )
}
