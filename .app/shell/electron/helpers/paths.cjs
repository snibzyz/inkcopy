const path = require('node:path')
const fs = require('node:fs')
const { app } = require('electron')

// App root — โฟลเดอร์ข้าง .exe (portable) หรือ workspace dir (dev)
function getAppRoot() {
  if (process.env.PORTABLE_EXECUTABLE_DIR) return process.env.PORTABLE_EXECUTABLE_DIR
  if (app.isPackaged) return path.dirname(process.execPath)
  return path.resolve(__dirname, '..', '..', '..', '..')
}

function ensureDir(p) {
  try { fs.mkdirSync(p, { recursive: true }) } catch { /* noop */ }
  return p
}

module.exports = { getAppRoot, ensureDir }
