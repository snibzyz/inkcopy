// Generic Electron main process — copy ไป <app>/electron/main.cjs
// แล้ว find-replace placeholders:
//   inkcopy     ชื่อแอปตัวเล็ก (เช่น inktts, inkidea) — ใช้กับ ipc namespace
//   5673     port ของ Vite dev (เช่น 5473) — ดู .shared/ports.md
//   1200      ความกว้าง default (เช่น 1200)
//   820      ความสูง default (เช่น 820)
//   1024  min width (เช่น 1024)
//   680  min height (เช่น 680)

const { app, BrowserWindow, shell, Menu } = require('electron')
const path = require('node:path')

if (app.isPackaged && process.resourcesPath) {
  process.env.NODE_PATH = path.join(process.resourcesPath, 'app.asar', 'node_modules')
  require('module').Module._initPaths()
}

const { registerWindowIpc } = require('./ipc/window.cjs')
const { registerFsIpc } = require('./ipc/fs.cjs')
const { registerClipboardIpc } = require('./ipc/clipboard.cjs')
const { registerDialogIpc } = require('./ipc/dialog.cjs')
const { registerSettingsIpc } = require('./ipc/settings.cjs')
const { registerLogIpc } = require('./ipc/log.cjs')
const { registerShellIpc } = require('./ipc/shell.cjs')
const { registerHotkeyIpc } = require('./ipc/hotkey.cjs')
const { registerPermissionsIpc } = require('./ipc/permissions.cjs')
const autoUpdate = require('./autoUpdate.cjs')
const { createLogger } = require('./helpers/logger.cjs')

const log = createLogger('main')
const isDev = process.env.NODE_ENV === 'development'
const isMac = process.platform === 'darwin'

let mainWindow = null

// กัน Electron default error dialog ครอบทุก uncaught — log อย่างเดียว
process.on('uncaughtException', (err) => {
  try { log.error('uncaughtException', { error: (err && err.stack) || String(err) }) } catch { /* noop */ }
})
process.on('unhandledRejection', (reason) => {
  try { log.error('unhandledRejection', { reason: (reason && reason.stack) || String(reason) }) } catch { /* noop */ }
})

function createMainWindow() {
  // INKCOPY is an always-on-top overlay anchored to the right edge of the
  // primary display, matching the Python PyQt6 layout. We open at the full
  // available height of the display (workArea = screen minus taskbar/dock)
  // so the chapter list can grow with the screen — no outer scrollbar even
  // with hundreds of chapters loaded.
  const { screen } = require('electron')
  const primary = screen.getPrimaryDisplay().workArea
  const winWidth = 720
  const winHeight = Math.max(640, primary.height - 24)

  mainWindow = new BrowserWindow({
    width: winWidth,
    height: winHeight,
    minWidth: 520,
    minHeight: 44,
    x: primary.x + primary.width - winWidth - 24,
    y: primary.y + 24,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: false,
    // Transparent shell so the rounded body + dim alpha background show
    // through to the desktop. Without this the chrome looks like a square
    // box and the minimized state stays a solid rectangle.
    transparent: true,
    backgroundColor: '#00000000',
    hasShadow: true,
    roundedCorners: true,
    resizable: true,
    show: false,
    icon: path.join(__dirname, '..', 'public', 'logo.ico'),
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  })

  mainWindow.once('ready-to-show', () => mainWindow.show())

  mainWindow.webContents.on('before-input-event', (event, input) => {
    if (input.type !== 'keyDown') return
    if (input.key === 'F12') {
      const wc = mainWindow.webContents
      if (wc.isDevToolsOpened()) wc.closeDevTools()
      else wc.openDevTools({ mode: 'detach' })
      event.preventDefault()
    } else if ((input.control || input.meta) && input.key.toLowerCase() === 'r' && !input.shift) {
      mainWindow.webContents.reload()
      event.preventDefault()
    }
  })

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  mainWindow.webContents.on('context-menu', (_event, params) => {
    const items = []
    if (params.selectionText && params.selectionText.trim()) items.push({ label: 'คัดลอก', role: 'copy' })
    if (params.editFlags && params.editFlags.canPaste) items.push({ label: 'วาง', role: 'paste' })
    if (params.editFlags && params.editFlags.canSelectAll) {
      items.push({ type: 'separator' })
      items.push({ label: 'เลือกทั้งหมด', role: 'selectAll' })
    }
    if (!items.length) return
    Menu.buildFromTemplate(items).popup({ window: mainWindow })
  })

  if (isDev) {
    mainWindow.loadURL('http://localhost:5673')
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))
  }
  return mainWindow
}

app.whenReady().then(() => {
  registerWindowIpc(() => mainWindow)
  registerFsIpc(() => mainWindow)
  registerClipboardIpc()
  registerDialogIpc(() => mainWindow)
  registerSettingsIpc()
  registerLogIpc()
  registerShellIpc()
  registerHotkeyIpc(() => mainWindow)
  registerPermissionsIpc()
  autoUpdate.registerIpc()

  createMainWindow()
  autoUpdate.start(mainWindow)
  log.info('app ready', { isDev, version: app.getVersion(), e2e: process.env.INKCOPY_E2E === '1' })

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createMainWindow()
  })
})

app.on('window-all-closed', () => { if (!isMac) app.quit() })

// ก่อนปิดจริง — ถ้ามี staged update รออยู่ → apply เงียบ ๆ (swap exe + restart)
let _quitting = false
app.on('before-quit', (event) => {
  if (_quitting) return
  try {
    const applied = autoUpdate.applyStagedOnQuit?.()
    if (applied) {
      _quitting = true
      event.preventDefault()
      log.info('staged update applying — app will relaunch via helper.cmd')
      setTimeout(() => app.exit(0), 300)
    }
  } catch (err) {
    log.warn('apply on quit failed', { error: err && err.message })
  }
})
