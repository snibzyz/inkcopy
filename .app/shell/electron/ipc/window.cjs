const { ipcMain, app } = require('electron')

function registerWindowIpc(getMainWindow) {
  ipcMain.handle('window:minimize', () => { getMainWindow()?.minimize() })
  ipcMain.handle('window:maximize', () => {
    const w = getMainWindow()
    if (!w) return
    if (w.isMaximized()) w.unmaximize()
    else w.maximize()
  })
  ipcMain.handle('window:close', () => { getMainWindow()?.close() })
  ipcMain.handle('window:isMaximized', () => getMainWindow()?.isMaximized() ?? false)
  ipcMain.handle('window:toggleDevTools', () => {
    const wc = getMainWindow()?.webContents
    if (!wc) return
    if (wc.isDevToolsOpened()) wc.closeDevTools()
    else wc.openDevTools({ mode: 'detach' })
  })
  ipcMain.handle('window:reload', () => { getMainWindow()?.webContents?.reload() })
  ipcMain.handle('window:setTitle', (_e, payload) => {
    const title = String(payload?.title ?? '')
    if (title) getMainWindow()?.setTitle(title)
  })
  // Resize without moving — used when the renderer "minimizes" the overlay
  // by collapsing the content. Keeps the top-right anchor stable so the
  // bar doesn't jump around the screen.
  ipcMain.handle('window:setHeight', (_e, payload) => {
    const w = getMainWindow()
    if (!w) return
    const target = Math.max(48, Math.min(1200, Number(payload?.height ?? 820)))
    const [width] = w.getSize()
    const [x, y] = w.getPosition()
    w.setBounds({ x, y, width, height: target })
  })
  ipcMain.on('app:getVersionSync', (event) => { event.returnValue = app.getVersion() })
}

module.exports = { registerWindowIpc }
