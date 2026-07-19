# INKCOPY — per-app memory

## Status (2026-07-19)

INKCOPY มี 2 implementation ขนานกัน — **ทั้งคู่ถูก release ผ่าน CI เดียวกัน**:

| Implementation | Path | สถานะ |
|---|---|---|
| **Python / PyQt6** (canonical) | `inkcopy.py` + `INKCOPY.spec` | ใช้งานจริง · เวอร์ชันเดินหน้าต่อ (ล่าสุด v0.3.2) |
| **Electron** | `.app/shell/` | **implement จริงแล้ว** ~5,600 บรรทัด · frozen ที่ v0.3.1 |

> **อย่าลบ `.app/shell/` เด็ดขาดโดยไม่ถามก่อน.** เอกสารเดิมเขียนว่า "scaffolded — ยังไม่มี
> implementation" ซึ่ง **ผิด** และเกือบทำให้ลบงานจริงทิ้ง (2026-07-19). ของจริงที่มี:
> 14 React components, IPC 8 ตัว (clipboard/hotkey/permissions/settings/dialog/shell/fs/window),
> Playwright E2E 5 ชุด + screenshot snapshots ทั้ง win32/darwin, 12 commits ฟีเจอร์.
> commit `ebac659` = paste/copy/next/prev/auto-switch + overlay ทำงานได้บน macOS แล้ว.

**กฎระหว่าง transition:**
- Bug ที่ user รายงาน → fix ใน Python ก่อน (canonical)
- Electron = frozen — ไม่ต้อง bump version พร้อม Python (ตั้งแต่ v0.3.2 เป็นต้นไป
  `.app/shell/package.json` ค้างที่ 0.3.1 โดยตั้งใจ เพราะโค้ดไม่ได้แก้)
- **release.yml: job `publish` ตั้ง `needs:` รวม electron-windows/electron-macos**
  → ถ้า Electron build พัง จะไม่มีอะไรถูก publish เลย รวมทั้ง Python. ปล่อย Python
  เดี่ยว ๆ ไม่ได้ถ้าไม่แก้ workflow ก่อน

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

- **2026-06-09**: mixed-paste fix #2 + responsive UI. (a) The 2026-06-08 fix hardened only the *text* write; files still went through Qt (`OleSetClipboard`), so the Qt-OLE owner kept fighting the native text write under the rapid text→file→text swaps and could re-leave stale FILE data (Gemini target). Fix: **route file writes through native `SetClipboardData(CF_HDROP)` too** (`_win32_set_clipboard_files`) so ONE ownership model is used; each write is post-verified with `IsClipboardFormatAvailable` + retried; this is the CF_HDROP idea from the reverted attempt but *clean* (no GetAsyncKeyState/scroll). Also: `event()` drops stray Ctrl+V while `_staged_sequence_active` (no double-advance), an 8s **watchdog** force-clears a stuck sequence, and Windows staged delays retuned for Gemini (after_user 300→350, clipboard→ctrl_v 60→90, after_text 150→250). Verified by a 27-check harness incl. an 8-round text↔file clipboard round-trip on real Win32. (b) **Responsive UI scaling** ([[inkcopy-ui-resize-preference]] — was deferred): single `ui_scale` factor scales the stylesheet (fonts/padding) + every fixed widget size + layout margins (NOT a scroll area). Title-bar `− 100% +` zoom controls + Ctrl+mouse-wheel; persisted as `ui_scale` in config (0.55–1.6). Visually verified via `QWidget.grab()` at 1.0/0.7/0.55.
- **2026-06-08**: fix mixed paste (prompt=file + chapter=text) where files stacked & chapter text went missing after a few rounds. Root cause: Windows text clipboard write went through Qt (`OleSetClipboard`) which fails silently under clipboard contention → stale FILE data left on clipboard. Now the **text** write uses native `SetClipboardData` (CF_UNICODETEXT) with an OpenClipboard retry loop (and correct 64-bit ctypes restypes). **File writes left on the existing Qt path untouched** — minimal, surgical change. (A broader earlier attempt — CF_HDROP files + GetAsyncKeyState + UI scroll — was reverted for making it worse.)
- **2026-05-26**: v0.2.2 — CGEventPost-based synthetic Cmd+V, Input Monitoring detection, DMG launch warning
- **2026-05-26**: Electron scaffold created at `.app/shell/` (no implementation yet)
- **2026-05-26**: v0.2.1 — fix macOS pynput crash + UTF-8 BOM on text outputs
- **2026-05-24**: v0.2.0 — diagnostics UI, NSIS installer, .dmg packaging, in-app auto-updater

<!-- ink-vault-pointer -->
## INK family — cross-project knowledge

แอปนี้เป็นส่วนหนึ่งของตระกูล INK. **ภาพรวม + ความเชื่อมโยงข้ามแอป** อยู่ใน Obsidian vault กลาง (path เต็มใช้ได้จากทุก worktree บนเครื่องนี้):
- `Z:/Mega Project/INK Vault/Home.md` — แผนผังครอบครัว INK (pipeline: INKCRAW→INKMAGIC/INKIDEA→INKTTS→INKREALM)
- `Z:/Mega Project/INK Vault/Apps/INKCOPY.md` — ภาพรวมแอปนี้ · `INK Vault/Topics/` — Shared System / Design / Electron / Infra
- docs structure มาตรฐาน (.claude (ซ่อน) + docs + implement) → `Z:/Mega Project/.shared/docs-structure.md`

เมื่อต้องเข้าใจภาพใหญ่ หรือทำงานคร่อมหลายแอป → อ่าน vault ก่อนลงมือ.
