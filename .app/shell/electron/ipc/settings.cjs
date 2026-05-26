// Generic JSON settings store — เก็บที่ <userData>/settings.json
// ใช้แบบ flat key หรือ nested ก็ได้ (setKey รองรับ dot-path)

const { ipcMain, app, BrowserWindow } = require('electron')
const fs = require('node:fs')
const path = require('node:path')

function getSettingsPath() {
  return path.join(app.getPath('userData'), 'settings.json')
}

function readAll() {
  try {
    const txt = fs.readFileSync(getSettingsPath(), 'utf-8')
    const parsed = JSON.parse(txt)
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function writeAll(obj) {
  try {
    fs.mkdirSync(path.dirname(getSettingsPath()), { recursive: true })
    fs.writeFileSync(getSettingsPath(), JSON.stringify(obj, null, 2), 'utf-8')
    return true
  } catch {
    return false
  }
}

// แจ้ง renderer ทุก window ว่า settings ถูกแก้ — ใช้ใน multi-window scenario
function broadcast(next) {
  for (const w of BrowserWindow.getAllWindows()) {
    if (!w.isDestroyed()) w.webContents.send('settings:changed', next)
  }
}

function setByPath(obj, dotPath, value) {
  const keys = String(dotPath).split('.').filter(Boolean)
  if (!keys.length) return obj
  let cur = obj
  for (let i = 0; i < keys.length - 1; i += 1) {
    const k = keys[i]
    if (!cur[k] || typeof cur[k] !== 'object') cur[k] = {}
    cur = cur[k]
  }
  cur[keys[keys.length - 1]] = value
  return obj
}

function registerSettingsIpc() {
  ipcMain.handle('settings:get', () => readAll())

  ipcMain.handle('settings:patch', (_e, partial) => {
    if (!partial || typeof partial !== 'object') return { ok: false, error: 'partial must be object' }
    const current = readAll()
    const next = { ...current, ...partial }
    const ok = writeAll(next)
    if (ok) broadcast(next)
    return { ok, settings: next }
  })

  ipcMain.handle('settings:setKey', (_e, payload) => {
    const key = String(payload?.key || '')
    if (!key) return { ok: false, error: 'key required' }
    const current = readAll()
    setByPath(current, key, payload?.value)
    const ok = writeAll(current)
    if (ok) broadcast(current)
    return { ok, settings: current }
  })

  ipcMain.handle('settings:reset', () => {
    const ok = writeAll({})
    if (ok) broadcast({})
    return { ok }
  })
}

module.exports = { registerSettingsIpc, readAll, writeAll, getSettingsPath }
