// INKCOPY hotkey IPC — stub implementation.
//
// Native global-hotkey wiring (uiohook-napi / CGEventPost / SendInput) is not
// yet bundled in the Electron shell; this stub satisfies the `window.inkcopy.hotkey.*`
// contract used by the renderer so the UI renders + tests run end-to-end.
// Replace with a real listener once the native module is integrated.

const { ipcMain } = require('electron')
const { createLogger } = require('../helpers/logger.cjs')

const log = createLogger('hotkey')

let _registered = false
const _stats = {
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

function registerHotkeyIpc(getMainWindow) {
  ipcMain.handle('hotkey:register', () => {
    _registered = true
    _stats.listenerStarted = true
    log.info('hotkey:register (stub) — native module not yet bundled')
    return { ok: true, reason: 'stub' }
  })

  ipcMain.handle('hotkey:unregister', () => {
    _registered = false
    _stats.listenerStarted = false
    log.info('hotkey:unregister (stub)')
    return undefined
  })

  ipcMain.handle('hotkey:sendPaste', () => {
    log.info('hotkey:sendPaste (stub) — would CGEventPost / SendInput in native build')
    return { ok: false }
  })

  ipcMain.handle('hotkey:stats', () => ({ ..._stats }))

  // ── test hooks (only active when INKCOPY_E2E=1) ───────────────────────
  // Lets Playwright drive the hotkey events without needing a native module
  // wired in. Mirrors the smartc test hooks pattern from INKIDEA.
  if (process.env.INKCOPY_E2E === '1') {
    ipcMain.handle('hotkey:_testFirePaste', () => {
      _stats.pasteFires += 1
      _stats.vKeysSeen += 1
      _stats.keysReceived += 1
      const win = getMainWindow()
      if (win) win.webContents.send('hotkey:paste')
      return undefined
    })
    ipcMain.handle('hotkey:_testFirePrev', () => {
      _stats.prevFires += 1
      const win = getMainWindow()
      if (win) win.webContents.send('hotkey:prev')
      return undefined
    })
    ipcMain.handle('hotkey:_testFireNext', () => {
      _stats.nextFires += 1
      const win = getMainWindow()
      if (win) win.webContents.send('hotkey:next')
      return undefined
    })
  }
}

module.exports = { registerHotkeyIpc }
