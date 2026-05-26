const { ipcMain, clipboard } = require('electron')

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
}

module.exports = { registerClipboardIpc }
