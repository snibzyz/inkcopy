import { useStore } from '../state/store'
import { Codicon } from '../ui/Codicon'

export function ConcurrentRow() {
  const concurrent = useStore((s) => s.concurrentChapters)
  const setConcurrentChapters = useStore((s) => s.setConcurrentChapters)

  return (
    <div className="flex items-center gap-2 rounded-sm border border-vscode-border bg-vscode-input/30 px-2.5 py-1.5 text-[13px]">
      <Codicon name="layers" size={11} className="text-vscode-muted" />
      <span className="text-vscode-muted">วางพร้อมกัน:</span>
      <input
        type="number"
        min={1}
        max={20}
        value={concurrent}
        onChange={(e) => {
          const v = parseInt(e.target.value, 10)
          if (Number.isFinite(v)) setConcurrentChapters(v)
        }}
        className="h-7 w-16 rounded-sm border border-vscode-border bg-vscode-input px-1.5 text-[13px] text-vscode-fg outline-none focus:border-vscode-focus"
        data-testid="concurrent-input"
      />
      <span className="text-vscode-muted">ตอน/รอบ</span>
    </div>
  )
}
