// Renderer → main bridge สำหรับเขียน log ไปยังไฟล์เดียวกับ main process

const { ipcMain } = require('electron')
const { createLogger, getLogPath } = require('../helpers/logger.cjs')

const renderer = createLogger('renderer')

function registerLogIpc() {
  ipcMain.handle('log:write', (_e, payload) => {
    const level = payload?.level || 'info'
    const scope = String(payload?.scope || 'unknown')
    const msg = String(payload?.msg || '')
    const data = payload?.data
    const fn = renderer[level] || renderer.info
    // override scope per-call: ใช้ writer ตัว renderer แต่ผนวก scope เข้าใน msg
    fn(`[${scope}] ${msg}`, data)
    return { ok: true }
  })
  ipcMain.handle('log:getPath', () => getLogPath())
}

module.exports = { registerLogIpc }
