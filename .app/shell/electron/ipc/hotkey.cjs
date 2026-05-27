// INKCOPY hotkey IPC — real global keyboard listener via uiohook-napi.
//
// Why uiohook-napi over Electron's globalShortcut: globalShortcut CONSUMES
// the matching hotkey, so registering Cmd+V/Ctrl+V would steal the OS paste
// behaviour. uiohook listens passively at the HID layer — events still flow
// to the focused app (Chrome/Gemini), and we just observe.
//
// On Windows: works out of the box once the prebuilt binary is loaded.
// On macOS:   requires the user grant the app "Accessibility" permission in
//             System Settings → Privacy & Security. Without it `uIOhook.start()`
//             throws, surfaced to the renderer via `{ ok: false, reason }`.

const { ipcMain } = require('electron')
const { execFile } = require('child_process')
const { createLogger } = require('../helpers/logger.cjs')

const log = createLogger('hotkey')

let uioh = null
try {
  uioh = require('uiohook-napi')
} catch (err) {
  log.warn('uiohook-napi not available — paste hotkeys disabled', { error: err && err.message })
}

let _started = false
let _mainWindowGetter = () => null
let _syntheticMuteUntil = 0
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

/**
 * Send an event to all renderer windows. Cheap fanout (we only have one
 * window today) but keeps the API symmetric with broadcast-style events.
 */
function emitToRenderer(channel, payload) {
  const win = _mainWindowGetter()
  if (win && !win.isDestroyed()) {
    win.webContents.send(channel, payload)
  }
}

function handleKeyDown(event) {
  if (Date.now() < _syntheticMuteUntil) return
  _stats.keysReceived += 1
  const kc = event.keycode
  const cmdHeld = !!event.metaKey
  const ctrlHeld = !!event.ctrlKey
  _stats.lastKeyRepr = `kc=${kc} ctrl=${ctrlHeld} cmd=${cmdHeld}`

  // Verbose log so the user can confirm the listener actually sees keys
  // ("permission appears ON but no events arrive" was the #1 failure mode
  // in the Python build too).
  log.info('keyDown', { kc, ctrlHeld, cmdHeld, alt: !!event.altKey, shift: !!event.shiftKey })

  if (!uioh) return
  const K = uioh.UiohookKey

  // Cmd+V (macOS) or Ctrl+V (Win/Linux) — paste trigger.
  if (kc === K.V) {
    _stats.vKeysSeen += 1
    const modifier = process.platform === 'darwin' ? cmdHeld : ctrlHeld
    if (modifier) {
      _stats.pasteFires += 1
      log.info('paste hotkey fired')
      emitToRenderer('hotkey:paste')
    }
    return
  }
  if (kc === K.F9) {
    _stats.prevFires += 1
    log.info('F9 → prev')
    emitToRenderer('hotkey:prev')
    return
  }
  if (kc === K.F10) {
    _stats.nextFires += 1
    log.info('F10 → next')
    emitToRenderer('hotkey:next')
    return
  }
  if (kc === K.F12) {
    _stats.pauseFires += 1
    log.info('F12 → pause')
    emitToRenderer('hotkey:pause')
    return
  }
}

function execFileWithTimeout(file, args, timeoutMs = 1500) {
  return new Promise((resolve) => {
    const child = execFile(file, args, { windowsHide: true, timeout: timeoutMs }, (error) => {
      if (error) {
        resolve({ ok: false, reason: error.message || String(error) })
        return
      }
      resolve({ ok: true })
    })
    child.on('error', (error) => {
      resolve({ ok: false, reason: error.message || String(error) })
    })
  })
}

async function sendSyntheticPaste() {
  _syntheticMuteUntil = Date.now() + 900
  if (process.env.INKCOPY_E2E === '1') return { ok: true, reason: 'e2e-stub' }

  if (process.platform === 'darwin') {
    return await execFileWithTimeout('/usr/bin/osascript', [
      '-e',
      'tell application "System Events" to keystroke "v" using command down',
    ])
  }

  if (process.platform === 'win32') {
    return await execFileWithTimeout('powershell.exe', [
      '-NoProfile',
      '-NonInteractive',
      '-Command',
      "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('^v')",
    ])
  }

  return await execFileWithTimeout('xdotool', ['key', 'ctrl+v'])
}

function startListener() {
  if (!uioh) return { ok: false, reason: 'uiohook-napi not loaded' }
  if (_started) return { ok: true, reason: 'already started' }
  try {
    uioh.uIOhook.on('keydown', handleKeyDown)
    uioh.uIOhook.start()
    _started = true
    _stats.listenerStarted = true
    _stats.lastError = ''
    log.info('uIOhook started')
    return { ok: true }
  } catch (err) {
    const message = (err && err.message) || String(err)
    _stats.lastError = message
    log.error('uIOhook start failed', { error: message })
    return { ok: false, reason: message }
  }
}

function stopListener() {
  if (!uioh || !_started) return
  try {
    uioh.uIOhook.off('keydown', handleKeyDown)
    uioh.uIOhook.stop()
  } catch (err) {
    log.warn('uIOhook stop error', { error: err && err.message })
  }
  _started = false
  _stats.listenerStarted = false
}

function registerHotkeyIpc(getMainWindow) {
  _mainWindowGetter = getMainWindow || (() => null)

  ipcMain.handle('hotkey:register', () => {
    // In E2E we use the test-only hotkey:_testFire* handlers and skip the
    // real uiohook listener so Playwright's synthetic keyboard events don't
    // get caught by both layers.
    if (process.env.INKCOPY_E2E === '1') {
      _stats.listenerStarted = true
      return { ok: true, reason: 'e2e-stub' }
    }
    return startListener()
  })
  ipcMain.handle('hotkey:unregister', () => {
    stopListener()
    return undefined
  })

  // Synthetic Cmd+V — used by the staged file-paste flow. uiohook events
  // include synthetic ones, so we cooperate by setting a brief mute window
  // while our own injected keystroke propagates.
  ipcMain.handle('hotkey:sendPaste', async () => {
    log.info('hotkey:sendPaste — synthetic injection')
    const result = await sendSyntheticPaste()
    if (!result.ok) log.warn('synthetic paste failed', { reason: result.reason })
    return result
  })

  ipcMain.handle('hotkey:stats', () => ({ ..._stats }))

  // ── E2E test hooks — only exposed when INKCOPY_E2E=1 ──────────────────
  if (process.env.INKCOPY_E2E === '1') {
    ipcMain.handle('hotkey:_testFirePaste', () => {
      _stats.pasteFires += 1
      _stats.vKeysSeen += 1
      _stats.keysReceived += 1
      emitToRenderer('hotkey:paste')
      return undefined
    })
    ipcMain.handle('hotkey:_testFirePrev', () => {
      _stats.prevFires += 1
      emitToRenderer('hotkey:prev')
      return undefined
    })
    ipcMain.handle('hotkey:_testFireNext', () => {
      _stats.nextFires += 1
      emitToRenderer('hotkey:next')
      return undefined
    })
  }
}

// Stop listener on process exit so the keyboard hook doesn't outlive the
// app (otherwise Windows leaves it dangling and uiohook complains on next
// launch about a stale hook).
process.on('exit', stopListener)
process.on('SIGINT', () => {
  stopListener()
  process.exit(0)
})

module.exports = { registerHotkeyIpc }
