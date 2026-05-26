const { ipcMain, clipboard, nativeImage } = require('electron')
const { createLogger } = require('../helpers/logger.cjs')

const log = createLogger('clipboard')

/**
 * Build a Windows CF_HDROP DROPFILES structure for one or more file paths.
 * Layout (from MSDN):
 *   DROPFILES {
 *     DWORD pFiles;     // offset to filename list = 20
 *     POINT pt;         // 8 bytes, zeroed
 *     BOOL  fNC;        // 4 bytes, zeroed
 *     BOOL  fWide;      // 4 bytes, 1 = UTF-16 filenames
 *   }
 *   <UTF-16LE filename>\0 <UTF-16LE filename>\0 ... \0
 *
 * Pastes into Explorer, Chrome upload widgets, Slack, etc. as if you'd
 * dragged the files from Explorer.
 */
function buildCfHdropBuffer(paths) {
  const header = Buffer.alloc(20)
  header.writeUInt32LE(20, 0) // pFiles offset
  // pt + fNC stay zero
  header.writeUInt32LE(1, 16) // fWide = 1

  const names = []
  for (const p of paths) names.push(Buffer.from(p + '\0', 'utf16le'))
  names.push(Buffer.from('\0', 'utf16le')) // final extra null terminator
  return Buffer.concat([header, ...names])
}

/**
 * Write file paths to the clipboard as native file references. Returns
 * { ok, count, kind }. Best-effort: when the native bridge isn't available
 * on a platform, falls back to writing the joined paths as plain text so the
 * user still gets *something*, then `ok=false` so the caller can show a hint.
 */
function writeFileUrls(paths) {
  if (!Array.isArray(paths) || !paths.length) return { ok: false, count: 0, kind: 'empty' }

  if (process.platform === 'win32') {
    try {
      const buf = buildCfHdropBuffer(paths)
      // Electron exposes the raw CF_HDROP format under the name 'CF_HDROP'
      // (Windows) and accepts a Node Buffer via clipboard.writeBuffer.
      clipboard.writeBuffer('CF_HDROP', buf)
      log.info('writeFileUrls CF_HDROP', { count: paths.length })
      return { ok: true, count: paths.length, kind: 'CF_HDROP' }
    } catch (err) {
      log.error('CF_HDROP write failed', { error: err && err.message })
    }
  }

  if (process.platform === 'darwin') {
    try {
      // NSFilenamesPboardType — historical but still recognised. Write the
      // property-list string array directly; AppKit-aware receivers will
      // pick it up. (A future native module can switch to the modern
      // public.file-url UTI via NSPasteboard.writeObjects:.)
      const plist =
        '<?xml version="1.0" encoding="UTF-8"?>\n' +
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n' +
        '<plist version="1.0"><array>' +
        paths.map((p) => `<string>${p.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</string>`).join('') +
        '</array></plist>'
      clipboard.writeBuffer('NSFilenamesPboardType', Buffer.from(plist, 'utf8'))
      log.info('writeFileUrls NSFilenamesPboardType', { count: paths.length })
      return { ok: true, count: paths.length, kind: 'NSFilenamesPboardType' }
    } catch (err) {
      log.error('NSFilenamesPboardType write failed', { error: err && err.message })
    }
  }

  // Linux / fallback — write file:// URIs as text. Most file managers paste
  // these as actual files when targeted at a folder window.
  clipboard.writeText(paths.map((p) => 'file://' + p.replace(/\\/g, '/')).join('\n'))
  return { ok: false, count: paths.length, kind: 'text-fallback' }
}

function registerClipboardIpc() {
  ipcMain.handle('clipboard:readText', () => clipboard.readText())

  ipcMain.handle('clipboard:writeText', (_e, payload) => {
    const text = String(payload?.text ?? '')
    clipboard.writeText(text)
    return { ok: true }
  })

  ipcMain.handle('clipboard:clear', () => {
    clipboard.clear()
    return { ok: true }
  })

  ipcMain.handle('clipboard:writeFiles', (_e, payload) => {
    const paths = Array.isArray(payload?.paths) ? payload.paths.map(String) : []
    return writeFileUrls(paths)
  })

  // Mixed: write file URLs first (the native format), then `clipboard.write`
  // with text augments the pasteboard's text fallback so a receiver that
  // doesn't understand file URLs still gets the joined chapter text.
  ipcMain.handle('clipboard:writeMixed', (_e, payload) => {
    const text = String(payload?.text ?? '')
    const paths = Array.isArray(payload?.files) ? payload.files.map(String) : []

    if (!paths.length && !text) {
      clipboard.clear()
      return { ok: true, kind: 'empty' }
    }
    if (!paths.length) {
      clipboard.writeText(text)
      return { ok: true, kind: 'text' }
    }

    const filesResult = writeFileUrls(paths)
    if (text) {
      // Append text without clobbering the file URLs we just wrote.
      // `clipboard.write({ text })` merges with existing pasteboard entries
      // on macOS; on Windows it actually clears prior formats, so on Win
      // we accept text-loss and rely on the staged Cmd+V flow (TODO).
      try {
        if (process.platform === 'darwin') {
          clipboard.write({ text }, 'clipboard')
        }
      } catch (err) {
        log.warn('mixed text append failed', { error: err && err.message })
      }
    }
    return { ok: filesResult.ok, kind: `mixed-${filesResult.kind}` }
  })
}

module.exports = { registerClipboardIpc }
