import { useStore } from '../state/store'
import type { PasteMode } from '../types/inkcopy'
import { Codicon } from '../ui/Codicon'
import { cn } from '../ui/cn'

const MODES: Array<{
  id: PasteMode
  label: string
  icon: string
  description: string
}> = [
  {
    id: 'paste',
    label: 'วาง · PASTE',
    icon: 'clippy',
    description: 'รวม Prompt + ตอน แล้ววางเข้า AI',
  },
  {
    id: 'copy',
    label: 'คัดลอก · COPY',
    icon: 'copy',
    description: 'รับข้อความที่ AI ตอบ → บันทึกไฟล์',
  },
  {
    id: 'vocab',
    label: 'ศัพท์ · VOCAB',
    icon: 'book',
    description: 'รวม clipboard เป็นไฟล์ศัพท์',
  },
]

export function ModeToggle() {
  const mode = useStore((s) => s.mode)
  const setMode = useStore((s) => s.setMode)

  return (
    <div className="grid grid-cols-3 gap-1 rounded-sm border border-vscode-border bg-vscode-input p-1">
      {MODES.map((m) => {
        const active = mode === m.id
        return (
          <button
            key={m.id}
            type="button"
            onClick={() => setMode(m.id)}
            className={cn(
              'flex flex-col items-start gap-0.5 rounded-sm px-2 py-1.5 text-left text-[13px] transition-colors',
              active
                ? 'bg-vscode-brand/15 text-vscode-brand'
                : 'text-vscode-fg hover:bg-vscode-list-hover',
            )}
            data-testid={`mode-${m.id}`}
            data-active={active}
          >
            <span className="flex items-center gap-1.5">
              <Codicon name={m.icon} size={12} />
              <span className="font-semibold tracking-[0.04em]">{m.label}</span>
            </span>
            <span className="pl-[18px] text-[13px] text-vscode-muted">{m.description}</span>
          </button>
        )
      })}
    </div>
  )
}
