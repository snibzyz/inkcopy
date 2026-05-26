// INKCOPY shared types — used by both renderer (zustand store, components) and
// the preload-bridge typings below. The window.inkcopy.* interface declared at
// the bottom mirrors electron/preload.cjs so calls are statically typed.

export type PasteMode = 'paste' | 'copy' | 'vocab'

export interface PromptFile {
  /** Display name (basename) */
  displayName: string
  /** Absolute path on disk (already resolved if it was a .lnk) */
  path: string
}

export interface ChapterFile {
  displayName: string
  path: string
  /** Auto-detected trailing chapter number if any (eg. "Episode_007.txt" → 7) */
  detectedNumber: number | null
}

export type ChapterRange = { lo: number | null; hi: number | null } | null

export interface HotkeyStats {
  keysReceived: number
  vKeysSeen: number
  pasteFires: number
  prevFires: number
  nextFires: number
  pauseFires: number
  lastKeyRepr: string
  lastError: string
  listenerStarted: boolean
}

export interface PermissionState {
  /** macOS only — null on win/linux */
  accessibilityTrusted: boolean | null
  /** macOS only — null on win/linux */
  inputMonitoringTrusted: boolean | null
  /** macOS only — true if launched from /Volumes/ (mounted DMG) */
  runningFromDmg: boolean
}

export interface UpdateInfo {
  available: boolean
  tag: string | null
  url: string | null
  artifactUrl: string | null
}

export type ToastTone = 'paste' | 'copy' | 'vocab' | 'info' | 'error'

export interface ToastEntry {
  id: string
  message: string
  tone: ToastTone
  durationMs: number
}

/* ─────────────────────────────────────────────────────────────────────────
 * window.inkcopy.* bridge — declared on the global Window interface so
 * components can call `window.inkcopy.fs.chooseFolder()` with full IntelliSense.
 * Mirrors electron/preload.cjs exposed object 1:1.
 * ──────────────────────────────────────────────────────────────────────── */

export interface FsChooseFolderOptions {
  title?: string
  defaultPath?: string
}

export interface FsChooseFilesOptions {
  title?: string
  filters?: Array<{ name: string; extensions: string[] }>
  defaultPath?: string
}

export interface FsListDirEntry {
  name: string
  path: string
  isDirectory: boolean
  isFile: boolean
  size: number
  modifiedMs: number
}

export interface InkcopyBridge {
  platform: NodeJS.Platform
  isMac: boolean
  isWin: boolean
  isLinux: boolean

  app: {
    version: string
    checkUpdate: () => Promise<{ available: boolean; tag: string | null; url: string | null }>
    applyUpdate: () => Promise<{ ok: boolean }>
    onUpdateAvailable: (handler: (info: UpdateInfo) => void) => () => void
    onUpdateProgress: (handler: (p: { percent: number; downloaded: number; total: number }) => void) => () => void
    onUpdateDownloaded: (handler: () => void) => () => void
    onUpdateError: (handler: (err: { message: string }) => void) => () => void
  }

  window: {
    minimize: () => Promise<void>
    maximize: () => Promise<void>
    close: () => Promise<void>
    isMaximized: () => Promise<boolean>
    toggleDevTools: () => Promise<void>
    reload: () => Promise<void>
    setTitle: (title: string) => Promise<void>
    /** Resize window height (kept at current top-right corner). */
    setHeight: (height: number) => Promise<void>
  }

  fs: {
    getAppRoot: () => Promise<string>
    join: (...parts: string[]) => Promise<string>
    chooseFolder: (opts?: FsChooseFolderOptions) => Promise<string | null>
    chooseFiles: (opts?: FsChooseFilesOptions) => Promise<string[]>
    chooseFile: (opts?: FsChooseFilesOptions) => Promise<string | null>
    readText: (filePath: string) => Promise<string>
    writeText: (filePath: string, content: string) => Promise<{ ok: boolean }>
    listDir: (dir: string, opts?: { recursive?: boolean }) => Promise<FsListDirEntry[]>
    revealFolder: (target: string) => Promise<void>
    openExternal: (url: string) => Promise<void>
    exists: (target: string) => Promise<boolean>
  }

  clipboard: {
    readText: () => Promise<string>
    writeText: (text: string) => Promise<{ ok: boolean }>
    /** macOS: write file URLs via NSPasteboard. Win: CF_HDROP. Returns true if at least 1 written. */
    writeFiles: (paths: string[]) => Promise<{ ok: boolean; count: number }>
    /** Mixed: text + file URLs in one clipboard write (best-effort; some receivers ignore text). */
    writeMixed: (payload: { text: string; files: string[] }) => Promise<{ ok: boolean }>
    clear: () => Promise<void>
  }

  hotkey: {
    /** Start listening for Cmd/Ctrl+V + F9/F10/F12. Returns false if permission missing. */
    register: () => Promise<{ ok: boolean; reason?: string }>
    unregister: () => Promise<void>
    /** Synthesize Cmd/Ctrl+V (CGEventPost on macOS, SendInput on Windows). */
    sendPaste: () => Promise<{ ok: boolean }>
    stats: () => Promise<HotkeyStats>
    onPaste: (handler: () => void) => () => void
    onPrev: (handler: () => void) => () => void
    onNext: (handler: () => void) => () => void
    onPause: (handler: () => void) => () => void
    onKeyEvent: (handler: (evt: { keycode: number; modifiers: number; cmdHeld: boolean }) => void) => () => void
  }

  permissions: {
    check: () => Promise<PermissionState>
    /** macOS: open the relevant Privacy & Security pane. No-op on win/linux. */
    openSettings: (which: 'accessibility' | 'inputMonitoring') => Promise<void>
  }

  settings: {
    get: () => Promise<Record<string, unknown>>
    patch: (partial: Record<string, unknown>) => Promise<void>
    setKey: (key: string, value: unknown) => Promise<void>
    reset: () => Promise<void>
    onChange: (handler: (snapshot: Record<string, unknown>) => void) => () => void
  }

  log: {
    info: (scope: string, msg: string, data?: unknown) => Promise<void>
    warn: (scope: string, msg: string, data?: unknown) => Promise<void>
    error: (scope: string, msg: string, data?: unknown) => Promise<void>
    debug: (scope: string, msg: string, data?: unknown) => Promise<void>
    getLogPath: () => Promise<string>
  }

  shell: {
    showItemInFolder: (target: string) => Promise<void>
    beep: () => Promise<void>
  }
}

declare global {
  interface Window {
    inkcopy: InkcopyBridge
  }
}

export {}
