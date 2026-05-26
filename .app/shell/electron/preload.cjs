// Generic Electron preload bridge — copy แล้ว find-replace inkcopy
// Renderer access ผ่าน window.inkcopy
//
// Namespaces (รวม base ที่ทุกแอป INK ควรมี):
//   app         — version + auto-update flow
//   window      — window controls (min/max/close/devtools/reload)
//   fs          — file system (picker + read/write text + list + stat + mkdir + reveal)
//   clipboard   — read/write text จาก clipboard
//   dialog      — message box + save-file picker
//   settings    — JSON store ใน userData (get/patch)
//   log         — write log จาก renderer ไปยัง main logger
//   shell       — showItemInFolder + beep
//
// เพิ่ม namespace เฉพาะแอปได้ตาม pattern เดียวกัน (เช่น tts, crawler, render)

const { contextBridge, ipcRenderer } = require('electron')

const invoke = (channel, ...args) => ipcRenderer.invoke(channel, ...args)

const subscribe = (channel, handler) => {
  const listener = (_event, payload) => handler(payload)
  ipcRenderer.on(channel, listener)
  return () => ipcRenderer.off(channel, listener)
}

contextBridge.exposeInMainWorld('inkcopy', {
  platform: process.platform,
  isMac: process.platform === 'darwin',
  isWin: process.platform === 'win32',
  isLinux: process.platform === 'linux',

  app: {
    /** sync — เรียกครั้งเดียวตอน boot, ไม่ต้อง await */
    version: ipcRenderer.sendSync('app:getVersionSync'),
    checkUpdate: () => invoke('app:checkUpdate'),
    applyUpdate: () => invoke('app:applyUpdate'),
    onUpdateAvailable: (handler) => subscribe('app:updateAvailable', handler),
    onUpdateProgress: (handler) => subscribe('app:updateProgress', handler),
    onUpdateDownloaded: (handler) => subscribe('app:updateDownloaded', handler),
    onUpdateError: (handler) => subscribe('app:updateError', handler),
  },

  window: {
    minimize: () => invoke('window:minimize'),
    maximize: () => invoke('window:maximize'),
    close: () => invoke('window:close'),
    isMaximized: () => invoke('window:isMaximized'),
    toggleDevTools: () => invoke('window:toggleDevTools'),
    reload: () => invoke('window:reload'),
    setTitle: (title) => invoke('window:setTitle', { title }),
  },

  fs: {
    /** Path helpers */
    getAppRoot: () => invoke('fs:getAppRoot'),
    join: (...parts) => invoke('fs:join', { parts }),

    /** File pickers (returns path string) */
    chooseFolder: (opts) => invoke('fs:chooseFolder', opts || {}),
    chooseFiles: (opts) => invoke('fs:chooseFiles', opts || {}),
    chooseFile: (opts) => invoke('fs:chooseFile', opts || {}),

    /** Read / write (UTF-8 text) */
    readText: (filePath) => invoke('fs:readText', { path: filePath }),
    writeText: (filePath, content) => invoke('fs:writeText', { path: filePath, content }),

    /** Read / write (binary as base64) */
    readBytes: (filePath) => invoke('fs:readBytes', { path: filePath }),
    writeBytes: (filePath, base64) => invoke('fs:writeBytes', { path: filePath, base64 }),

    /** Directory ops */
    listDir: (dir, opts) => invoke('fs:listDir', { dir, ...(opts || {}) }),
    mkdir: (dir) => invoke('fs:mkdir', { path: dir }),
    rm: (target, opts) => invoke('fs:rm', { path: target, ...(opts || {}) }),
    rename: (from, to) => invoke('fs:rename', { from, to }),
    stat: (target) => invoke('fs:stat', { path: target }),
    exists: (target) => invoke('fs:exists', { path: target }),

    /** Shell helpers */
    revealFolder: (target) => invoke('fs:revealFolder', { path: target }),
    openExternal: (url) => invoke('fs:openExternal', { url }),
  },

  clipboard: {
    readText: () => invoke('clipboard:readText'),
    writeText: (text) => invoke('clipboard:writeText', { text }),
    /** ล้าง clipboard */
    clear: () => invoke('clipboard:clear'),
  },

  dialog: {
    /** kind: 'info' | 'warning' | 'error' | 'question' */
    message: (opts) => invoke('dialog:message', opts || {}),
    confirm: (opts) => invoke('dialog:confirm', opts || {}),
    saveFile: (opts) => invoke('dialog:saveFile', opts || {}),
  },

  settings: {
    /** ดึง settings ทั้งก้อน (returns {}) */
    get: () => invoke('settings:get'),
    /** merge partial เข้ากับของเดิม + persist ทันที */
    patch: (partial) => invoke('settings:patch', partial),
    /** เซ็ตค่าเดียวตาม path เช่น setKey('audio.volume', 0.5) */
    setKey: (key, value) => invoke('settings:setKey', { key, value }),
    /** reset ทั้งหมด */
    reset: () => invoke('settings:reset'),
    /** subscribe เมื่อมีการแก้ settings (จาก main หรือ renderer ตัวอื่น) */
    onChange: (handler) => subscribe('settings:changed', handler),
  },

  log: {
    info: (scope, msg, data) => invoke('log:write', { level: 'info', scope, msg, data }),
    warn: (scope, msg, data) => invoke('log:write', { level: 'warn', scope, msg, data }),
    error: (scope, msg, data) => invoke('log:write', { level: 'error', scope, msg, data }),
    debug: (scope, msg, data) => invoke('log:write', { level: 'debug', scope, msg, data }),
    getLogPath: () => invoke('log:getPath'),
  },

  shell: {
    /** เปิด File Explorer แล้ว highlight ไฟล์นี้ (ไม่ใช่เปิด parent) */
    showItemInFolder: (target) => invoke('shell:showItemInFolder', { path: target }),
    beep: () => invoke('shell:beep'),
  },

  // ─── เพิ่ม namespace ของแอปคุณตรงนี้ ────────────────────────────────────
  // เช่น:
  //   tts: { start, cancel, onEvent, ... }
  //   crawler: { fetch, listSites, ... }
  //   render: { encode, preview, ... }
})
