# INKCOPY — per-app memory

## Status (2026-05-26)

INKCOPY มี 2 implementation ขนานกัน:

| Implementation | Path | สถานะ |
|---|---|---|
| **Python / PyQt6** (canonical) | `inkcopy.py` + `INKCOPY.spec` | ใช้งานจริง — release ผ่าน CI (`.exe` + `.dmg`) |
| **Electron** (WIP) | `.app/shell/` | scaffolded จาก `.shared/` — ยังไม่มี feature parity |

**กฎระหว่าง transition:**
- Bug ที่ user รายงาน → fix ใน Python ก่อน (canonical)
- Feature ใหม่ → ลง Electron port (เพื่อไม่ทับซ้อนทำงานคู่)
- เมื่อ Electron มี feature parity ครบ → Python deprecate

## Python (canonical)

- Entry: [inkcopy.py](../inkcopy.py)
- Hotkey backend แยกตาม platform:
  - Windows: `keyboard` library (low-latency Win32 hooks)
  - macOS: `NSEvent.addGlobalMonitorForEventsMatchingMask:` + `CGEventPost` synthesize
  - Linux: `pynput`
- macOS ต้อง granted **ทั้ง** Accessibility + Input Monitoring (Catalina+)
- macOS app **ต้องอยู่ใน /Applications/** ไม่ใช่ /Volumes/ (DMG) — TCC จะไม่ remember permissions
- Build: PyInstaller via GitHub Actions (`.github/workflows/release.yml` triggered โดย tag `v*`)

## Electron (WIP — `.app/shell/`)

- ใช้ template ตาม [.shared/](../../.shared/) เต็มรูปแบบ
- Vite port: **5673** (ดู [.shared/ports.md](../../.shared/ports.md))
- Window namespace IPC: `window.inkcopy.*`
- Dev: `pnpm dev` ที่ root ของแอป

**สิ่งที่ Electron port ต้องทำให้ได้ก่อน parity:**

1. **Global Cmd/Ctrl+V detection** — ต้อง native module (`uiohook-napi`) เพราะ Electron `globalShortcut` กิน hotkey ทิ้ง — Electron API ไม่ pass through
2. **NSPasteboard file URLs** — native code (Objective-C wrapper หรือ ctypes-equivalent) สำหรับ `public.file-url` UTI
3. **Synthetic Cmd/Ctrl+V** — บน macOS: CGEventPost via `node-mac-permissions` หรือ AppleScript shell-out; บน Windows: SendInput via `node-key-sender`
4. **F9 / F10 / F12 hotkeys** สำหรับ prev / next / pause
5. **Chapter folder + file ordering** ตาม natsort logic ของ Python version
6. **Config persistence** — `~/Library/Application Support/INKCOPY/config.json` (macOS) / `%APPDATA%\INKCOPY\config.json` (Windows)
7. **Auto-updater** ตาม pattern `.shared/electron/autoUpdate.cjs` + `portableUpdate.cjs`

**ที่ Electron จะดีกว่า Python:**
- ไม่เจอ SSL cert verify failed ตอน update check บน macOS frozen build
- ไม่ต้อง maintain PyInstaller + py2app + DMG codesign quirks
- UI ใช้ `.shared/ui/` ตรง ๆ — เข้าฝักตระกูล INK

## UI ของ Python (สำหรับ reference ตอน port)

- Top-right overlay, frameless, always-on-top
- 3 modes: PASTE / COPY / VOCAB (ปุ่ม toggle ด้านบน)
- Status row, diagnostics row (hotkey health + permission)
- Prompt folder + Prompt files list (per-file toggle: text vs file URL)
- Chapter folder + range filter
- Output folder (COPY mode)
- Pause / Hotkeys / Open log buttons

## Recent changes

- **2026-05-26**: v0.2.2 — CGEventPost-based synthetic Cmd+V, Input Monitoring detection, DMG launch warning
- **2026-05-26**: Electron scaffold created at `.app/shell/` (no implementation yet)
- **2026-05-26**: v0.2.1 — fix macOS pynput crash + UTF-8 BOM on text outputs
- **2026-05-24**: v0.2.0 — diagnostics UI, NSIS installer, .dmg packaging, in-app auto-updater
