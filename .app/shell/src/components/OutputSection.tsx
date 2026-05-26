import { useStore } from '../state/store'
import { Codicon } from '../ui/Codicon'
import { MacFieldLabel } from '../ui/MacFieldLabel'

export function OutputSection() {
  const folder = useStore((s) => s.outputFolder)
  const copyTemplateEnabled = useStore((s) => s.copyTemplateEnabled)
  const setOutputFolder = useStore((s) => s.setOutputFolder)
  const setCopyTemplateEnabled = useStore((s) => s.setCopyTemplateEnabled)

  const chooseFolder = async () => {
    const next = await window.inkcopy.fs.chooseFolder({ title: 'เลือก Output folder' })
    if (next) setOutputFolder(next)
  }

  return (
    <section className="space-y-2" data-testid="output-section">
      <MacFieldLabel>โฟลเดอร์ปลายทาง (โหมด COPY)</MacFieldLabel>
      <div className="flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          onClick={chooseFolder}
          className="flex h-8 items-center gap-1.5 rounded-sm border border-vscode-border bg-vscode-button px-2.5 text-[13px] text-vscode-fg hover:bg-vscode-list-hover"
          data-testid="output-folder-btn"
        >
          <Codicon name="folder-opened" size={12} />
          <span>โฟลเดอร์ปลายทาง</span>
        </button>
        <label className="ml-auto flex items-center gap-1.5 text-[13px] text-vscode-muted">
          <input
            type="checkbox"
            checked={copyTemplateEnabled}
            onChange={(e) => setCopyTemplateEnabled(e.target.checked)}
            className="accent-vscode-brand"
          />
          <span>ใส่ title + บรรทัดว่างก่อนเนื้อหา</span>
        </label>
      </div>
      <div className="text-[13px] text-vscode-muted" data-testid="output-info">
        {folder ? (
          <span className="block truncate" title={folder}>
            <Codicon name="folder" size={11} /> {folder}
          </span>
        ) : (
          <span>ยังไม่ได้เลือกโฟลเดอร์ปลายทาง</span>
        )}
      </div>
    </section>
  )
}
