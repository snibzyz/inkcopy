const { ipcMain, dialog } = require('electron')

function registerDialogIpc(getMainWindow) {
  /**
   * Generic message box
   * payload: { kind, title, message, detail, buttons, defaultId, cancelId }
   *   kind: 'info' | 'warning' | 'error' | 'question'
   */
  ipcMain.handle('dialog:message', async (_e, payload) => {
    const r = await dialog.showMessageBox(getMainWindow(), {
      type: payload?.kind || 'info',
      title: payload?.title || '',
      message: String(payload?.message || ''),
      detail: payload?.detail ? String(payload.detail) : undefined,
      buttons: Array.isArray(payload?.buttons) ? payload.buttons : ['ตกลง'],
      defaultId: typeof payload?.defaultId === 'number' ? payload.defaultId : 0,
      cancelId: typeof payload?.cancelId === 'number' ? payload.cancelId : undefined,
      noLink: true,
    })
    return { response: r.response, checkboxChecked: r.checkboxChecked }
  })

  /**
   * Confirm dialog — returns { confirmed: boolean }
   * payload: { title, message, detail, okLabel, cancelLabel, destructive }
   */
  ipcMain.handle('dialog:confirm', async (_e, payload) => {
    const ok = String(payload?.okLabel || 'ตกลง')
    const cancel = String(payload?.cancelLabel || 'ยกเลิก')
    const r = await dialog.showMessageBox(getMainWindow(), {
      type: payload?.destructive ? 'warning' : 'question',
      title: payload?.title || '',
      message: String(payload?.message || ''),
      detail: payload?.detail ? String(payload.detail) : undefined,
      buttons: [ok, cancel],
      defaultId: 0,
      cancelId: 1,
      noLink: true,
    })
    return { confirmed: r.response === 0 }
  })

  /**
   * Save-file picker — returns path or null
   * payload: { defaultPath, filters, title }
   */
  ipcMain.handle('dialog:saveFile', async (_e, payload) => {
    const r = await dialog.showSaveDialog(getMainWindow(), {
      defaultPath: payload?.defaultPath,
      filters: payload?.filters || [{ name: 'All', extensions: ['*'] }],
      title: payload?.title || 'บันทึกเป็น',
    })
    return r.canceled ? null : r.filePath
  })
}

module.exports = { registerDialogIpc }
