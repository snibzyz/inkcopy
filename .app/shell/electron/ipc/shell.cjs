const { ipcMain, shell } = require('electron')
const fs = require('node:fs')

function registerShellIpc() {
  /** เปิด File Explorer แล้ว highlight target (ต่างจาก revealFolder ที่เปิด target ตรง ๆ) */
  ipcMain.handle('shell:showItemInFolder', (_e, payload) => {
    const target = String(payload?.path || '')
    if (!target || !fs.existsSync(target)) return { ok: false, error: 'path not found' }
    shell.showItemInFolder(target)
    return { ok: true }
  })

  ipcMain.handle('shell:beep', () => {
    shell.beep()
    return { ok: true }
  })
}

module.exports = { registerShellIpc }
