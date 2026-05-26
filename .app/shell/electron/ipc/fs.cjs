const { ipcMain, dialog, shell } = require('electron')
const fs = require('node:fs')
const fsp = require('node:fs/promises')
const path = require('node:path')
const { getAppRoot } = require('../helpers/paths.cjs')

function registerFsIpc(getMainWindow) {
  ipcMain.handle('fs:getAppRoot', () => ({ appRoot: getAppRoot() }))

  ipcMain.handle('fs:join', (_e, payload) => {
    const parts = Array.isArray(payload?.parts) ? payload.parts.map(String) : []
    return path.join(...parts)
  })

  // ─── Pickers ────────────────────────────────────────────────────────────
  ipcMain.handle('fs:chooseFolder', async (_e, payload) => {
    const r = await dialog.showOpenDialog(getMainWindow(), {
      properties: ['openDirectory'],
      defaultPath: payload?.defaultPath || getAppRoot(),
      title: payload?.title || 'เลือกโฟลเดอร์',
    })
    return r.canceled ? null : r.filePaths[0]
  })

  ipcMain.handle('fs:chooseFiles', async (_e, payload) => {
    const r = await dialog.showOpenDialog(getMainWindow(), {
      properties: ['openFile', 'multiSelections'],
      defaultPath: payload?.defaultPath || getAppRoot(),
      filters: payload?.filters || [{ name: 'All', extensions: ['*'] }],
      title: payload?.title || 'เลือกไฟล์',
    })
    return r.canceled ? [] : r.filePaths
  })

  ipcMain.handle('fs:chooseFile', async (_e, payload) => {
    const r = await dialog.showOpenDialog(getMainWindow(), {
      properties: ['openFile'],
      defaultPath: payload?.defaultPath || getAppRoot(),
      filters: payload?.filters || [{ name: 'All', extensions: ['*'] }],
      title: payload?.title || 'เลือกไฟล์',
    })
    return r.canceled ? null : r.filePaths[0]
  })

  // ─── Text I/O ───────────────────────────────────────────────────────────
  ipcMain.handle('fs:readText', async (_e, payload) => {
    const p = String(payload?.path || '')
    if (!p) return { ok: false, error: 'path required' }
    try {
      const content = await fsp.readFile(p, 'utf-8')
      return { ok: true, content }
    } catch (err) {
      return { ok: false, error: err && err.message }
    }
  })

  ipcMain.handle('fs:writeText', async (_e, payload) => {
    const p = String(payload?.path || '')
    if (!p) return { ok: false, error: 'path required' }
    try {
      await fsp.mkdir(path.dirname(p), { recursive: true })
      await fsp.writeFile(p, String(payload?.content ?? ''), 'utf-8')
      return { ok: true }
    } catch (err) {
      return { ok: false, error: err && err.message }
    }
  })

  // ─── Binary (base64) ────────────────────────────────────────────────────
  ipcMain.handle('fs:readBytes', async (_e, payload) => {
    const p = String(payload?.path || '')
    if (!p) return { ok: false, error: 'path required' }
    try {
      const buf = await fsp.readFile(p)
      return { ok: true, base64: buf.toString('base64') }
    } catch (err) {
      return { ok: false, error: err && err.message }
    }
  })

  ipcMain.handle('fs:writeBytes', async (_e, payload) => {
    const p = String(payload?.path || '')
    const base64 = String(payload?.base64 || '')
    if (!p) return { ok: false, error: 'path required' }
    try {
      await fsp.mkdir(path.dirname(p), { recursive: true })
      await fsp.writeFile(p, Buffer.from(base64, 'base64'))
      return { ok: true }
    } catch (err) {
      return { ok: false, error: err && err.message }
    }
  })

  // ─── Directory ops ──────────────────────────────────────────────────────
  ipcMain.handle('fs:listDir', async (_e, payload) => {
    const dir = String(payload?.dir || '')
    const ext = payload?.ext ? String(payload.ext).toLowerCase().replace(/^\./, '') : null
    const onlyFiles = payload?.onlyFiles !== false   // default true
    if (!dir || !fs.existsSync(dir)) return []
    try {
      const entries = await fsp.readdir(dir, { withFileTypes: true })
      return entries
        .filter((e) => {
          if (onlyFiles && !e.isFile()) return false
          if (ext && !e.name.toLowerCase().endsWith(`.${ext}`)) return false
          return true
        })
        .map((e) => ({
          name: e.name,
          path: path.join(dir, e.name),
          isDirectory: e.isDirectory(),
          isFile: e.isFile(),
        }))
        .sort((a, b) => a.name.localeCompare(b.name))
    } catch {
      return []
    }
  })

  ipcMain.handle('fs:mkdir', async (_e, payload) => {
    const p = String(payload?.path || '')
    if (!p) return { ok: false, error: 'path required' }
    try {
      await fsp.mkdir(p, { recursive: true })
      return { ok: true }
    } catch (err) {
      return { ok: false, error: err && err.message }
    }
  })

  ipcMain.handle('fs:rm', async (_e, payload) => {
    const p = String(payload?.path || '')
    if (!p) return { ok: false, error: 'path required' }
    try {
      await fsp.rm(p, { recursive: !!payload?.recursive, force: !!payload?.force })
      return { ok: true }
    } catch (err) {
      return { ok: false, error: err && err.message }
    }
  })

  ipcMain.handle('fs:rename', async (_e, payload) => {
    const from = String(payload?.from || '')
    const to = String(payload?.to || '')
    if (!from || !to) return { ok: false, error: 'from + to required' }
    try {
      await fsp.rename(from, to)
      return { ok: true }
    } catch (err) {
      return { ok: false, error: err && err.message }
    }
  })

  ipcMain.handle('fs:stat', async (_e, payload) => {
    const p = String(payload?.path || '')
    if (!p) return null
    try {
      const s = await fsp.stat(p)
      return {
        size: s.size,
        isFile: s.isFile(),
        isDirectory: s.isDirectory(),
        mtimeMs: s.mtimeMs,
        ctimeMs: s.ctimeMs,
      }
    } catch {
      return null
    }
  })

  ipcMain.handle('fs:exists', (_e, payload) => {
    const p = String(payload?.path || '')
    return p ? fs.existsSync(p) : false
  })

  // ─── Shell helpers ──────────────────────────────────────────────────────
  ipcMain.handle('fs:revealFolder', async (_e, payload) => {
    const target = String(payload?.path || '')
    if (!target) return false
    try {
      if (!fs.existsSync(target)) fs.mkdirSync(target, { recursive: true })
      shell.openPath(target)
      return true
    } catch {
      return false
    }
  })

  ipcMain.handle('fs:openExternal', (_e, payload) => {
    const url = String(payload?.url || '')
    if (!url) return false
    shell.openExternal(url)
    return true
  })
}

module.exports = { registerFsIpc }
