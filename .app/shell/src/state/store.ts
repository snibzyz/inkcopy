import { create } from 'zustand'
import type {
  PasteMode,
  PromptFile,
  ChapterFile,
  ChapterRange,
  HotkeyStats,
  PermissionState,
  UpdateInfo,
  ToastEntry,
} from '../types/inkcopy'

const INITIAL_HOTKEY_STATS: HotkeyStats = {
  keysReceived: 0,
  vKeysSeen: 0,
  pasteFires: 0,
  prevFires: 0,
  nextFires: 0,
  pauseFires: 0,
  lastKeyRepr: '',
  lastError: '',
  listenerStarted: false,
}

const INITIAL_PERMISSIONS: PermissionState = {
  accessibilityTrusted: null,
  inputMonitoringTrusted: null,
  runningFromDmg: false,
}

const INITIAL_UPDATE: UpdateInfo = {
  available: false,
  tag: null,
  url: null,
  artifactUrl: null,
}

/**
 * Single-store layout copied from INKTTS — INKCOPY is a single-purpose tool
 * so the granular per-feature stores INKIDEA uses would be overkill.
 *
 * State maps 1:1 to SmartClipboardOverlay attributes in inkcopy.py so the
 * Python flow can be translated section-by-section without re-deriving names.
 */
export interface AppState {
  // ── Mode + global ──────────────────────────────────────────────────────
  mode: PasteMode
  paused: boolean
  minimized: boolean

  // ── Folders + files (PASTE mode) ───────────────────────────────────────
  promptFolder: string | null
  promptFiles: PromptFile[]
  /** Per-prompt-file: true = paste as text, false = paste as file URL. */
  promptPasteModes: Record<string, boolean>
  includePrompt: boolean

  // ── Chapters (PASTE + COPY mode) ───────────────────────────────────────
  chapterFolder: string | null
  /** Currently-visible chapter list (may be range-filtered). */
  chapterFiles: ChapterFile[]
  /** Full list before range filter — restored when filter clears. */
  allChapterFiles: ChapterFile[]
  chapterRange: ChapterRange
  chapterPasteAsText: boolean
  includeChapter: boolean
  currentIndex: number
  concurrentChapters: number

  // ── COPY mode ─────────────────────────────────────────────────────────
  outputFolder: string | null
  copyTemplateEnabled: boolean

  // ── VOCAB mode ────────────────────────────────────────────────────────
  vocabFilename: string
  vocabEntryCount: number

  // ── Staged paste (mixed: text + files) ────────────────────────────────
  stagedPendingFilePaths: string[] | null
  stagedSequenceActive: boolean
  /** Tuning knobs (ms) — exposed via settings.json. */
  stagedMsAfterUserPaste: number
  stagedMsClipboardToCtrlV: number
  stagedMsAfterTextPaste: number
  stagedMsSimplePaste: number

  // ── Diagnostics / hotkey ──────────────────────────────────────────────
  hotkeysRegistered: boolean
  hotkeyStats: HotkeyStats
  permissions: PermissionState

  // ── Update + toast ────────────────────────────────────────────────────
  update: UpdateInfo
  toasts: ToastEntry[]

  // ── Actions ───────────────────────────────────────────────────────────
  setMode: (mode: PasteMode) => void
  togglePaused: () => void
  toggleMinimized: () => void

  setPromptFolder: (folder: string | null, files: PromptFile[]) => void
  setPromptFiles: (files: PromptFile[]) => void
  removePromptFile: (path: string) => void
  setPromptPasteMode: (displayName: string, asText: boolean) => void
  /** Bulk-set every prompt + chapter to text or file mode in one shot. */
  setAllPasteModes: (asText: boolean) => void
  setIncludePrompt: (include: boolean) => void

  setChapterFolder: (folder: string | null, files: ChapterFile[]) => void
  setChapterRange: (range: ChapterRange) => void
  setChapterPasteAsText: (asText: boolean) => void
  setIncludeChapter: (include: boolean) => void
  setCurrentIndex: (idx: number) => void
  advanceChapter: (count: number) => void
  setConcurrentChapters: (n: number) => void

  setOutputFolder: (folder: string | null) => void
  setCopyTemplateEnabled: (enabled: boolean) => void

  setVocabFilename: (name: string) => void
  incrementVocabEntryCount: () => void

  setStagedPendingFilePaths: (paths: string[] | null) => void
  setStagedSequenceActive: (active: boolean) => void

  setHotkeysRegistered: (registered: boolean) => void
  setHotkeyStats: (stats: Partial<HotkeyStats>) => void
  setPermissions: (perm: Partial<PermissionState>) => void

  setUpdate: (info: Partial<UpdateInfo>) => void

  showToast: (toast: Omit<ToastEntry, 'id'> & { id?: string }) => void
  dismissToast: (id: string) => void
}

let _toastCounter = 0

export const useStore = create<AppState>((set, _get) => ({
  // ── Initial state ────────────────────────────────────────────────────
  mode: 'paste',
  paused: false,
  minimized: false,

  promptFolder: null,
  promptFiles: [],
  promptPasteModes: {},
  includePrompt: true,

  chapterFolder: null,
  chapterFiles: [],
  allChapterFiles: [],
  chapterRange: null,
  chapterPasteAsText: false,
  includeChapter: true,
  currentIndex: 0,
  concurrentChapters: 1,

  outputFolder: null,
  copyTemplateEnabled: true,

  vocabFilename: 'vocab.txt',
  vocabEntryCount: 0,

  stagedPendingFilePaths: null,
  stagedSequenceActive: false,
  stagedMsAfterUserPaste: 300,
  stagedMsClipboardToCtrlV: 60,
  stagedMsAfterTextPaste: 150,
  stagedMsSimplePaste: 90,

  hotkeysRegistered: false,
  hotkeyStats: INITIAL_HOTKEY_STATS,
  permissions: INITIAL_PERMISSIONS,

  update: INITIAL_UPDATE,
  toasts: [],

  // ── Actions ─────────────────────────────────────────────────────────
  setMode: (mode) => set({ mode }),
  togglePaused: () => set((s) => ({ paused: !s.paused })),
  toggleMinimized: () => set((s) => ({ minimized: !s.minimized })),

  setPromptFolder: (folder, files) => set({ promptFolder: folder, promptFiles: files }),
  setPromptFiles: (files) => set({ promptFiles: files }),
  removePromptFile: (path) =>
    set((s) => ({
      promptFiles: s.promptFiles.filter((f) => f.path !== path),
      // Drop any stale per-file paste-mode entry tied to this file.
      promptPasteModes: Object.fromEntries(
        Object.entries(s.promptPasteModes).filter(([name]) =>
          s.promptFiles.some((f) => f.path !== path && f.displayName === name),
        ),
      ),
    })),
  setPromptPasteMode: (displayName, asText) =>
    set((s) => ({ promptPasteModes: { ...s.promptPasteModes, [displayName]: asText } })),
  setAllPasteModes: (asText) =>
    set((s) => ({
      promptPasteModes: Object.fromEntries(s.promptFiles.map((f) => [f.displayName, asText])),
      chapterPasteAsText: asText,
    })),
  setIncludePrompt: (include) => set({ includePrompt: include }),

  setChapterFolder: (folder, files) =>
    set({
      chapterFolder: folder,
      chapterFiles: files,
      allChapterFiles: files,
      chapterRange: null,
      currentIndex: 0,
    }),
  setChapterRange: (range) =>
    set((s) => {
      if (!range || (range.lo === null && range.hi === null)) {
        return { chapterRange: null, chapterFiles: s.allChapterFiles, currentIndex: 0 }
      }
      const filtered = s.allChapterFiles.filter((ch) => {
        if (ch.detectedNumber === null) return false
        if (range.lo !== null && ch.detectedNumber < range.lo) return false
        if (range.hi !== null && ch.detectedNumber > range.hi) return false
        return true
      })
      return { chapterRange: range, chapterFiles: filtered, currentIndex: 0 }
    }),
  setChapterPasteAsText: (asText) => set({ chapterPasteAsText: asText }),
  setIncludeChapter: (include) => set({ includeChapter: include }),
  setCurrentIndex: (idx) => set({ currentIndex: idx }),
  advanceChapter: (count) =>
    set((s) => ({ currentIndex: Math.min(s.currentIndex + count, s.chapterFiles.length) })),
  setConcurrentChapters: (n) => set({ concurrentChapters: Math.max(1, Math.min(20, n)) }),

  setOutputFolder: (folder) => set({ outputFolder: folder }),
  setCopyTemplateEnabled: (enabled) => set({ copyTemplateEnabled: enabled }),

  setVocabFilename: (name) => set({ vocabFilename: name }),
  incrementVocabEntryCount: () => set((s) => ({ vocabEntryCount: s.vocabEntryCount + 1 })),

  setStagedPendingFilePaths: (paths) => set({ stagedPendingFilePaths: paths }),
  setStagedSequenceActive: (active) => set({ stagedSequenceActive: active }),

  setHotkeysRegistered: (registered) => set({ hotkeysRegistered: registered }),
  setHotkeyStats: (stats) => set((s) => ({ hotkeyStats: { ...s.hotkeyStats, ...stats } })),
  setPermissions: (perm) => set((s) => ({ permissions: { ...s.permissions, ...perm } })),

  setUpdate: (info) => set((s) => ({ update: { ...s.update, ...info } })),

  showToast: (toast) =>
    set((s) => {
      _toastCounter += 1
      const id = toast.id ?? `t${_toastCounter}`
      const entry: ToastEntry = {
        id,
        message: toast.message,
        tone: toast.tone,
        durationMs: toast.durationMs,
      }
      return { toasts: [...s.toasts, entry] }
    }),
  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}))
