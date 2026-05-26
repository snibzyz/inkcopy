import { useStore, type AppState } from '../state/store'
import { detectChapterNumber, naturalCompare } from './chapters'
import type { ChapterFile, PromptFile, PasteMode, ChapterRange } from '../types/inkcopy'

/**
 * Schema of what lives in <userData>/settings.json. All fields optional —
 * any missing key falls back to the store's initial value.
 *
 * Two distinct ways the prompt list is captured:
 *   - `promptFolder` set + `promptFilePaths` empty → re-list the folder on
 *     startup (covers the "เลือกโฟลเดอร์" flow where adding files later means
 *     re-scanning gives the freshest list)
 *   - `promptFilePaths` populated → restore exactly those paths (covers the
 *     "ไฟล์… / เพิ่ม" picker flow where the user curated a specific set,
 *     possibly from multiple folders)
 *
 * Mirrors load_config / save_config in inkcopy.py 1:1 in spirit.
 */
interface PersistedSettings {
  mode?: PasteMode
  promptFolder?: string | null
  promptFilePaths?: string[]
  promptPasteModes?: Record<string, boolean>
  includePrompt?: boolean
  chapterFolder?: string | null
  chapterRange?: ChapterRange
  chapterPasteAsText?: boolean
  includeChapter?: boolean
  currentIndex?: number
  concurrentChapters?: number
  outputFolder?: string | null
  copyTemplateEnabled?: boolean
  vocabFilename?: string
}

const TEXT_PROMPT_EXTS = new Set(['.txt', '.md', '.json', '.csv', '.xml', '.html', '.htm'])
const CHAPTER_EXTS = new Set(['.txt', '.md'])

function isPromptCandidate(name: string): boolean {
  const dot = name.lastIndexOf('.')
  if (dot < 0) return false
  const ext = name.slice(dot).toLowerCase()
  return TEXT_PROMPT_EXTS.has(ext) || ext === '.lnk'
}

function isChapterCandidate(name: string): boolean {
  const dot = name.lastIndexOf('.')
  if (dot < 0) return false
  return CHAPTER_EXTS.has(name.slice(dot).toLowerCase())
}

function basename(path: string): string {
  return path.split(/[\\/]/).pop() ?? path
}

async function listPromptFiles(folder: string): Promise<PromptFile[]> {
  const entries = await window.inkcopy.fs.listDir(folder, { recursive: false })
  return entries
    .filter((e) => e.isFile && isPromptCandidate(e.name))
    .sort((a, b) => naturalCompare(a.name, b.name))
    .map<PromptFile>((e) => ({ displayName: e.name, path: e.path }))
}

async function listChapterFiles(folder: string): Promise<ChapterFile[]> {
  const entries = await window.inkcopy.fs.listDir(folder, { recursive: false })
  return entries
    .filter((e) => e.isFile && isChapterCandidate(e.name))
    .sort((a, b) => naturalCompare(a.name, b.name))
    .map<ChapterFile>((e) => ({
      displayName: e.name,
      path: e.path,
      detectedNumber: detectChapterNumber(e.name),
    }))
}

/** Resolve a list of explicit file paths into PromptFile records, skipping
 *  any that no longer exist on disk (folder was moved/deleted etc). */
async function resolvePromptPaths(paths: string[]): Promise<PromptFile[]> {
  const checks = await Promise.all(
    paths.map(async (p) => {
      try {
        return (await window.inkcopy.fs.exists(p)) ? p : null
      } catch {
        return null
      }
    }),
  )
  return checks
    .filter((p): p is string => !!p)
    .sort(naturalCompare)
    .map<PromptFile>((p) => ({ displayName: basename(p), path: p }))
}

/**
 * Load settings.json → hydrate store. Re-lists folders so the file lists
 * reflect what's on disk now, not what was there at last save. Safe to call
 * once at app boot.
 */
export async function hydrateFromSettings(): Promise<void> {
  let raw: PersistedSettings = {}
  try {
    raw = (await window.inkcopy.settings.get()) as PersistedSettings
  } catch {
    return
  }
  if (!raw || typeof raw !== 'object') return

  const s = useStore.getState()

  if (raw.mode === 'paste' || raw.mode === 'copy' || raw.mode === 'vocab') {
    s.setMode(raw.mode)
  }

  // Prompt — explicit file paths take precedence, else re-list the folder.
  if (raw.promptFilePaths && raw.promptFilePaths.length) {
    const files = await resolvePromptPaths(raw.promptFilePaths)
    s.setPromptFolder(raw.promptFolder ?? null, files)
  } else if (raw.promptFolder) {
    try {
      const files = await listPromptFiles(raw.promptFolder)
      s.setPromptFolder(raw.promptFolder, files)
    } catch {
      /* folder may have been deleted — leave empty */
    }
  }
  if (raw.promptPasteModes && typeof raw.promptPasteModes === 'object') {
    for (const [name, asText] of Object.entries(raw.promptPasteModes)) {
      s.setPromptPasteMode(name, !!asText)
    }
  }
  if (typeof raw.includePrompt === 'boolean') s.setIncludePrompt(raw.includePrompt)

  // Chapter — re-list folder, then re-apply range filter + currentIndex
  if (raw.chapterFolder) {
    try {
      const files = await listChapterFiles(raw.chapterFolder)
      s.setChapterFolder(raw.chapterFolder, files)
      if (raw.chapterRange) s.setChapterRange(raw.chapterRange)
      // currentIndex applied AFTER setChapterFolder (which resets it to 0)
      if (typeof raw.currentIndex === 'number') {
        const filteredLen = useStore.getState().chapterFiles.length
        s.setCurrentIndex(Math.max(0, Math.min(raw.currentIndex, filteredLen)))
      }
    } catch {
      /* folder gone — leave empty */
    }
  }
  if (typeof raw.chapterPasteAsText === 'boolean') s.setChapterPasteAsText(raw.chapterPasteAsText)
  if (typeof raw.includeChapter === 'boolean') s.setIncludeChapter(raw.includeChapter)
  if (typeof raw.concurrentChapters === 'number') s.setConcurrentChapters(raw.concurrentChapters)

  // COPY mode
  if (raw.outputFolder !== undefined) s.setOutputFolder(raw.outputFolder)
  if (typeof raw.copyTemplateEnabled === 'boolean') s.setCopyTemplateEnabled(raw.copyTemplateEnabled)

  // VOCAB mode
  if (raw.vocabFilename) s.setVocabFilename(raw.vocabFilename)
}

function snapshotForPersist(state: AppState): PersistedSettings {
  return {
    mode: state.mode,
    promptFolder: state.promptFolder,
    promptFilePaths: state.promptFiles.map((f) => f.path),
    promptPasteModes: state.promptPasteModes,
    includePrompt: state.includePrompt,
    chapterFolder: state.chapterFolder,
    chapterRange: state.chapterRange,
    chapterPasteAsText: state.chapterPasteAsText,
    includeChapter: state.includeChapter,
    currentIndex: state.currentIndex,
    concurrentChapters: state.concurrentChapters,
    outputFolder: state.outputFolder,
    copyTemplateEnabled: state.copyTemplateEnabled,
    vocabFilename: state.vocabFilename,
  }
}

function shallowEqualSettings(a: PersistedSettings, b: PersistedSettings): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}

/**
 * Subscribe to the store and debounce-persist relevant fields. Returns an
 * unsubscribe function (call in App.tsx cleanup). The 300ms debounce keeps
 * the disk write off the hot path while still feeling instant — Python's
 * inkcopy.py persists on every change synchronously, which is fine when the
 * config is ~1KB.
 */
export function startAutosave(): () => void {
  let last = snapshotForPersist(useStore.getState())
  let timer: number | null = null
  let cancelled = false

  const unsubscribe = useStore.subscribe((state) => {
    const next = snapshotForPersist(state)
    if (shallowEqualSettings(last, next)) return
    last = next
    if (timer !== null) window.clearTimeout(timer)
    timer = window.setTimeout(() => {
      if (cancelled) return
      void window.inkcopy.settings.patch(next as unknown as Record<string, unknown>)
    }, 300)
  })

  return () => {
    cancelled = true
    if (timer !== null) window.clearTimeout(timer)
    unsubscribe()
  }
}
