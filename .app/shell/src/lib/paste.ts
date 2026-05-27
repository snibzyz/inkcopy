import type { AppState } from '../state/store'

export interface PastePayload {
  /** Combined text payload (already joined with blank-line separators). */
  text: string
  /** Absolute file paths to write to clipboard as file URLs. */
  files: string[]
  /** Number of chapters this paste covers — used to advance currentIndex. */
  chapterCount: number
  /** Human-readable label for the toast ("ch001 … ch004"). */
  toastLabel: string
}

/**
 * Composes the clipboard payload for the next paste — pure function over
 * store state. Mirrors `_load_clipboard_paste_mode` in inkcopy.py:
 *   1. Walk prompt files in order, classify each as text or file URL.
 *   2. Walk `concurrent_chapters` chapters from currentIndex.
 *   3. Join all "text" pieces with "\n\n" → text payload.
 *   4. Collect all "file" pieces → files payload.
 *
 * Returns null when there's nothing pasteable (no chapter selected, paused,
 * include flags both off, etc.) so the caller can short-circuit.
 */
export async function buildPastePayload(state: AppState): Promise<PastePayload | null> {
  if (state.paused) return null
  if (state.mode !== 'paste') return null
  if (!state.chapterFiles.length) return null
  if (state.currentIndex >= state.chapterFiles.length) return null

  const remaining = state.chapterFiles.length - state.currentIndex
  const chapterCount = Math.min(state.concurrentChapters, remaining)

  const textParts: string[] = []
  const files: string[] = []

  if (state.includePrompt) {
    for (const promptFile of state.promptFiles) {
      const asText = state.promptPasteModes[promptFile.displayName] ?? false
      if (asText) {
        try {
          const content = await window.inkcopy.fs.readText(promptFile.path)
          textParts.push(content)
        } catch {
          // Skip unreadable prompt — don't block the whole paste.
        }
      } else {
        files.push(promptFile.path)
      }
    }
  }

  if (state.includeChapter) {
    for (let i = 0; i < chapterCount; i += 1) {
      const ch = state.chapterFiles[state.currentIndex + i]
      if (state.chapterPasteAsText) {
        try {
          const content = await window.inkcopy.fs.readText(ch.path)
          textParts.push(content)
        } catch {
          /* skip */
        }
      } else {
        files.push(ch.path)
      }
    }
  }

  const text = textParts.join('\n\n')

  const first = state.chapterFiles[state.currentIndex]?.displayName
  const last =
    chapterCount > 1 ? state.chapterFiles[state.currentIndex + chapterCount - 1]?.displayName : null
  const trim = (n?: string) => (n ? n.replace(/\.[^.]+$/, '') : '')
  const toastLabel = last ? `${trim(first)} … ${trim(last)}` : trim(first)

  return { text, files, chapterCount, toastLabel }
}

/**
 * Pushes a payload to the system clipboard. Returns the kind that was
 * actually written so the caller can log it.
 *
 * Strategy:
 *   - Both text + files: prefer the native mixed write (NSPasteboard /
 *     CF_HDROP). If the native bridge isn't available, fall back to text-only
 *     (matches Python's "stage text first, synthetic Cmd+V files second" but
 *     the staged synthesis lives in the main process).
 *   - Files only: native writeFiles.
 *   - Text only: standard clipboard.writeText.
 */
export interface ClipboardWriteResult {
  kind: 'staged-mixed' | 'files' | 'text' | 'empty'
  stagedFiles: string[] | null
}

export async function writePayloadToClipboard(payload: PastePayload): Promise<ClipboardWriteResult> {
  const hasText = payload.text.length > 0
  const hasFiles = payload.files.length > 0
  if (!hasText && !hasFiles) {
    await window.inkcopy.clipboard.clear()
    return { kind: 'empty', stagedFiles: null }
  }
  if (hasText && hasFiles) {
    // Deterministic mixed paste: preload text now, then after the user's
    // Cmd/Ctrl+V the hotkey handler swaps clipboard to files and injects one
    // synthetic paste. Many web upload targets ignore either text or files
    // when both are on the same clipboard transaction.
    await window.inkcopy.clipboard.writeText(payload.text)
    return { kind: 'staged-mixed', stagedFiles: payload.files }
  }
  if (hasFiles) {
    await window.inkcopy.clipboard.writeFiles(payload.files)
    return { kind: 'files', stagedFiles: null }
  }
  await window.inkcopy.clipboard.writeText(payload.text)
  return { kind: 'text', stagedFiles: null }
}
