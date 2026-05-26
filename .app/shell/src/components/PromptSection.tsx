import { useStore } from '../state/store'
import type { PromptFile } from '../types/inkcopy'
import { naturalCompare } from '../lib/chapters'
import { Codicon } from '../ui/Codicon'
import { MacFieldLabel } from '../ui/MacFieldLabel'
import { PromptFileRow } from './PromptFileRow'

const TEXT_EXTS = new Set(['.txt', '.md', '.json', '.csv', '.xml', '.html', '.htm'])

function isPromptCandidate(name: string): boolean {
  const dot = name.lastIndexOf('.')
  if (dot < 0) return false
  const ext = name.slice(dot).toLowerCase()
  return TEXT_EXTS.has(ext) || ext === '.lnk'
}

async function listPromptsInFolder(folder: string): Promise<PromptFile[]> {
  const entries = await window.inkcopy.fs.listDir(folder, { recursive: false })
  return entries
    .filter((e) => e.isFile && isPromptCandidate(e.name))
    .sort((a, b) => naturalCompare(a.name, b.name))
    .map<PromptFile>((e) => ({ displayName: e.name, path: e.path }))
}

/**
 * Prompt folder section — port of `_select_prompt`, `_select_prompt_files_picker`,
 * `_add_prompt_files_picker` in inkcopy.py. Shows the folder path, exposes a
 * scrollable list of prompt files with per-row text/file toggle, and an
 * "include prompt" master checkbox.
 */
export function PromptSection() {
  const folder = useStore((s) => s.promptFolder)
  const files = useStore((s) => s.promptFiles)
  const includePrompt = useStore((s) => s.includePrompt)
  const setIncludePrompt = useStore((s) => s.setIncludePrompt)
  const setPromptFolder = useStore((s) => s.setPromptFolder)
  const setPromptFiles = useStore((s) => s.setPromptFiles)

  const chooseFolder = async () => {
    const next = await window.inkcopy.fs.chooseFolder({ title: 'เลือก Prompt folder' })
    if (!next) return
    const list = await listPromptsInFolder(next)
    setPromptFolder(next, list)
  }

  const choosePromptFiles = async (additive: boolean) => {
    const picked = await window.inkcopy.fs.chooseFiles({
      title: additive ? 'เพิ่ม Prompt files' : 'เลือก Prompt files',
      filters: [
        { name: 'Text', extensions: ['txt', 'md', 'json', 'csv', 'xml', 'html', 'htm'] },
        { name: 'Shortcut', extensions: ['lnk'] },
        { name: 'All files', extensions: ['*'] },
      ],
    })
    if (!picked.length) return
    const next: PromptFile[] = picked.map((p) => ({
      displayName: p.split(/[\\/]/).pop()!,
      path: p,
    }))
    if (additive) {
      const seen = new Set(files.map((f) => f.path))
      const merged = [...files, ...next.filter((f) => !seen.has(f.path))]
      merged.sort((a, b) => naturalCompare(a.displayName, b.displayName))
      setPromptFiles(merged)
    } else {
      next.sort((a, b) => naturalCompare(a.displayName, b.displayName))
      setPromptFolder(null, next)
    }
  }

  return (
    <section className="space-y-2" data-testid="prompt-section">
      <div className="flex items-center gap-2">
        <MacFieldLabel>ข้อความ Prompt</MacFieldLabel>
        <span className="text-[13px] text-vscode-muted">
          (คำสั่งให้ AI · ไฟล์ที่จะอ่านก่อนเริ่มแต่ละบท)
        </span>
        <label className="ml-auto flex items-center gap-1.5 text-[13px] text-vscode-muted">
          <input
            type="checkbox"
            checked={includePrompt}
            onChange={(e) => setIncludePrompt(e.target.checked)}
            className="accent-vscode-brand"
          />
          <span>ส่งด้วย</span>
        </label>
      </div>

      <div className="flex flex-wrap gap-1.5">
        <button
          type="button"
          onClick={chooseFolder}
          className="flex h-8 items-center gap-1.5 rounded-sm border border-vscode-border bg-vscode-button px-2.5 text-[13px] text-vscode-fg hover:bg-vscode-list-hover"
          data-testid="prompt-folder-btn"
        >
          <Codicon name="folder-opened" size={12} />
          <span>โฟลเดอร์</span>
        </button>
        <button
          type="button"
          onClick={() => choosePromptFiles(false)}
          className="flex h-8 items-center gap-1.5 rounded-sm border border-vscode-border bg-vscode-button px-2.5 text-[13px] text-vscode-fg hover:bg-vscode-list-hover"
          data-testid="prompt-files-btn"
        >
          <Codicon name="files" size={12} />
          <span>ไฟล์…</span>
        </button>
        <button
          type="button"
          onClick={() => choosePromptFiles(true)}
          className="flex h-8 items-center gap-1.5 rounded-sm border border-vscode-border bg-vscode-button px-2.5 text-[13px] text-vscode-fg hover:bg-vscode-list-hover"
          data-testid="prompt-add-btn"
        >
          <Codicon name="add" size={12} />
          <span>เพิ่ม</span>
        </button>
        <div className="ml-auto flex items-center gap-1 text-[13px] text-vscode-muted" data-testid="prompt-info">
          {folder ? (
            <span className="max-w-[220px] truncate" title={folder}>
              <Codicon name="folder" size={11} /> {folder}
            </span>
          ) : files.length ? (
            <span>{files.length} ไฟล์</span>
          ) : (
            <span>—</span>
          )}
        </div>
      </div>

      {files.length ? (
        <div className="max-h-[180px] space-y-1 overflow-y-auto rounded-sm border border-vscode-border bg-vscode-input/30 p-1.5">
          {files.map((f) => (
            <PromptFileRow key={f.path} file={f} />
          ))}
        </div>
      ) : (
        <div className="rounded-sm border border-dashed border-vscode-border bg-vscode-input/20 px-3 py-4 text-center text-[13px] text-vscode-muted">
          ยังไม่ได้เลือก prompt — กดปุ่ม "โฟลเดอร์" หรือ "ไฟล์…"
        </div>
      )}
    </section>
  )
}
