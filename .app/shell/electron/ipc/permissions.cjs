// INKCOPY permissions IPC — macOS Accessibility + Input Monitoring checks.
// On Windows/Linux returns null for both — the diagnostic UI handles nulls
// by hiding those bits.

const { ipcMain, shell, systemPreferences } = require('electron')
const { createLogger } = require('../helpers/logger.cjs')

const log = createLogger('permissions')

function checkAccessibility() {
  if (process.platform !== 'darwin') return null
  try {
    return systemPreferences.isTrustedAccessibilityClient(false)
  } catch (err) {
    log.warn('isTrustedAccessibilityClient failed', { error: err && err.message })
    return null
  }
}

function checkInputMonitoring() {
  if (process.platform !== 'darwin') return null
  try {
    // Electron exposes media access checks; Input Monitoring isn't one of the
    // standard buckets so we use a best-effort heuristic: when Accessibility
    // is granted but raw key events aren't observed by uiohook, the gap is
    // almost always Input Monitoring. Until the native module reports back
    // we surface null ("unknown") so the diagnostic UI prompts the user to
    // verify manually rather than misreport.
    return null
  } catch (err) {
    log.warn('input monitoring check failed', { error: err && err.message })
    return null
  }
}

function runningFromDmg() {
  if (process.platform !== 'darwin') return false
  const exe = process.execPath || ''
  return exe.includes('/Volumes/')
}

function registerPermissionsIpc() {
  ipcMain.handle('permissions:check', () => ({
    accessibilityTrusted: checkAccessibility(),
    inputMonitoringTrusted: checkInputMonitoring(),
    runningFromDmg: runningFromDmg(),
  }))

  ipcMain.handle('permissions:openSettings', (_event, payload) => {
    if (process.platform !== 'darwin') return
    const which = payload && payload.which
    const pane =
      which === 'inputMonitoring'
        ? 'x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent'
        : 'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility'
    shell.openExternal(pane).catch((err) => {
      log.warn('open settings failed', { error: err && err.message })
    })
  })
}

module.exports = { registerPermissionsIpc }
