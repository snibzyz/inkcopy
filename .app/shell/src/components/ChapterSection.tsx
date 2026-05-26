import { useState } from 'react'
import { useStore } from '../state/store'
import type { ChapterFile, ChapterRange } from '../types/inkcopy'
import { detectChapterNumber, naturalCompare } from '../lib/chapters'
import { Codicon } from '../ui/Codicon'
import { MacFieldLabel } from '../ui/MacFieldLabel'
import { cn } from '../ui/cn'

const CHAPTER_EXTS = new Set(['.txt', '.md'])

async function listChaptersInFolder(folder: string): Promise<ChapterFile[]> {
  const entries = await window.inkcopy.fs.listDir(folder, { recursive: false })
  return entries
    .filter((e) => {
      if (!e.isFile) return false
      const dot = e.name.lastIndexOf('.')
      if (dot < 0) return false
      return CHAPTER_EXTS.has(e.name.slice(dot).toLowerCase())
    })
    .sort((a, b) => naturalCompare(a.name, b.name))
    .map<ChapterFile>((e) => ({
      displayName: e.name,
      path: e.path,
      detectedNumber: detectChapterNumber(e.name),
    }))
}

export function ChapterSection() {
  const folder = useStore((s) => s.chapterFolder)
  const files = useStore((s) => s.chapterFiles)
  const allFiles = useStore((s) => s.allChapterFiles)
  const range = useStore((s) => s.chapterRange)
  const chapterPasteAsText = useStore((s) => s.chapterPasteAsText)
  const includeChapter = useStore((s) => s.includeChapter)
  const currentIndex = useStore((s) => s.currentIndex)
  const setChapterFolder = useStore((s) => s.setChapterFolder)
  const setChapterRange = useStore((s) => s.setChapterRange)
  const setChapterPasteAsText = useStore((s) => s.setChapterPasteAsText)
  const setIncludeChapter = useStore((s) => s.setIncludeChapter)
  const setCurrentIndex = useStore((s) => s.setCurrentIndex)

  const [loInput, setLoInput] = useState<string>(range?.lo?.toString() ?? '')
  const [hiInput, setHiInput] = useState<string>(range?.hi?.toString() ?? '')

  const chooseFolder = async () => {
    const next = await window.inkcopy.fs.chooseFolder({ title: 'เลือก Chapter folder' })
    if (!next) return
    const list = await listChaptersInFolder(next)
    setChapterFolder(next, list)
    setLoInput('')
    setHiInput('')
  }

  const applyRange = () => {
    const lo = loInput.trim() ? parseInt(loInput.trim(), 10) : null
    const hi = hiInput.trim() ? parseInt(hiInput.trim(), 10) : null
    const next: ChapterRange = lo === null && hi === null ? null : { lo, hi }
    setChapterRange(next)
  }

  const clearRange = () => {
    setLoInput('')
    setHiInput('')
    setChapterRange(null)
  }

  return (
    <section className="space-y-2" data-testid="chapter-section">
      <div className="flex items-center gap-2">
        <MacFieldLabel>ตอนนิยาย</MacFieldLabel>
        <span className="text-[13px] text-vscode-muted">
          (ไฟล์ตอนที่จะวางเข้าหา AI ทีละบท)
        </span>
        <label className="ml-auto flex items-center gap-1.5 text-[13px] text-vscode-muted">
          <input
            type="checkbox"
            checked={includeChapter}
            onChange={(e) => setIncludeChapter(e.target.checked)}
            className="accent-vscode-brand"
          />
          <span>ส่งด้วย</span>
        </label>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          onClick={chooseFolder}
          className="flex h-8 items-center gap-1.5 rounded-sm border border-vscode-border bg-vscode-button px-2.5 text-[13px] text-vscode-fg hover:bg-vscode-list-hover"
          data-testid="chapter-folder-btn"
        >
          <Codicon name="folder-opened" size={12} />
          <span>โฟลเดอร์</span>
        </button>

        <div className="flex shrink-0 overflow-hidden rounded-sm border border-vscode-border">
          <button
            type="button"
            onClick={() => setChapterPasteAsText(false)}
            className={cn(
              'h-8 px-2 text-[13px]',
              !chapterPasteAsText
                ? 'bg-vscode-brand/15 text-vscode-brand'
                : 'text-vscode-muted hover:bg-vscode-list-hover',
            )}
            data-testid="chapter-as-file"
          >
            ไฟล์
          </button>
          <button
            type="button"
            onClick={() => setChapterPasteAsText(true)}
            className={cn(
              'h-8 px-2 text-[13px]',
              chapterPasteAsText
                ? 'bg-vscode-brand/15 text-vscode-brand'
                : 'text-vscode-muted hover:bg-vscode-list-hover',
            )}
            data-testid="chapter-as-text"
          >
            ข้อความ
          </button>
        </div>

        <div className="ml-auto flex items-center gap-1 text-[13px] text-vscode-muted" data-testid="chapter-info">
          {folder ? (
            <span className="max-w-[220px] truncate" title={folder}>
              <Codicon name="folder" size={11} /> {folder}
            </span>
          ) : (
            <span>—</span>
          )}
        </div>
      </div>

      <div className="flex items-center gap-1.5 rounded-sm border border-vscode-border bg-vscode-input/30 px-2 py-1.5 text-[13px]">
        <Codicon name="filter" size={11} className="text-vscode-muted" />
        <span className="text-vscode-muted">เลือกช่วงตอน:</span>
        <input
          type="number"
          value={loInput}
          onChange={(e) => setLoInput(e.target.value)}
          onBlur={applyRange}
          placeholder="จากบทที่"
          className="h-7 w-20 rounded-sm border border-vscode-border bg-vscode-input px-1.5 text-[13px] text-vscode-fg outline-none focus:border-vscode-focus"
          data-testid="range-lo"
        />
        <span className="text-vscode-muted">→</span>
        <input
          type="number"
          value={hiInput}
          onChange={(e) => setHiInput(e.target.value)}
          onBlur={applyRange}
          placeholder="ถึงบทที่"
          className="h-7 w-20 rounded-sm border border-vscode-border bg-vscode-input px-1.5 text-[13px] text-vscode-fg outline-none focus:border-vscode-focus"
          data-testid="range-hi"
        />
        <button
          type="button"
          onClick={applyRange}
          className="h-7 rounded-sm border border-vscode-border bg-vscode-button px-2 text-[13px] text-vscode-fg hover:bg-vscode-list-hover"
          data-testid="range-apply"
        >
          ใช้
        </button>
        {range ? (
          <button
            type="button"
            onClick={clearRange}
            className="h-7 rounded-sm border border-vscode-border bg-vscode-button px-2 text-[13px] text-vscode-fg hover:bg-vscode-list-hover"
            data-testid="range-clear"
          >
            ล้าง
          </button>
        ) : null}
        <span className="ml-auto text-vscode-muted" data-testid="chapter-count">
          {files.length} / {allFiles.length} ตอน
        </span>
      </div>

      {files.length ? (
        <div className="max-h-[140px] overflow-y-auto rounded-sm border border-vscode-border bg-vscode-input/30 p-1">
          {files.map((f, idx) => (
            <button
              key={f.path}
              type="button"
              onClick={() => setCurrentIndex(idx)}
              className={cn(
                'flex w-full items-center gap-1.5 rounded-sm px-2 py-0.5 text-left text-[13px]',
                idx === currentIndex
                  ? 'bg-vscode-brand/20 text-vscode-brand'
                  : idx < currentIndex
                    ? 'text-vscode-muted hover:bg-vscode-list-hover'
                    : 'text-vscode-fg hover:bg-vscode-list-hover',
              )}
              data-testid="chapter-row"
              data-current={idx === currentIndex}
            >
              <Codicon
                name={idx < currentIndex ? 'check' : idx === currentIndex ? 'arrow-right' : 'circle-outline'}
                size={10}
                className="shrink-0"
              />
              <span className="flex-1 truncate" title={f.path}>
                {f.displayName}
              </span>
              {f.detectedNumber !== null ? (
                <span className="shrink-0 text-vscode-muted">#{f.detectedNumber}</span>
              ) : null}
            </button>
          ))}
        </div>
      ) : (
        <div className="rounded-sm border border-dashed border-vscode-border bg-vscode-input/20 px-3 py-4 text-center text-[13px] text-vscode-muted">
          ยังไม่ได้เลือกโฟลเดอร์ตอน
        </div>
      )}
    </section>
  )
}
