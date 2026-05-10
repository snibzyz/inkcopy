# INKCOPY

<p align="center">
  <img src="assets/inkcopy.png" alt="INKCOPY" width="180" />
</p>

โปรแกรมคลิปบอร์ดอัจฉริยะสำหรับนักเขียน สร้างขึ้นมาเพื่อช่วยในการจัดการไฟล์ Prompt และ Chapter ในการเขียนนิยาย/เนื้อหาแบบอัตโนมัติ

**Repository:** [https://github.com/snibzyz/inkcopy](https://github.com/snibzyz/inkcopy)

## ดาวน์โหลด (พร้อมใช้)

โหลดตัวล่าสุดจากหน้า [Releases](https://github.com/snibzyz/inkcopy/releases/latest):

- **Windows:** `INKCOPY.exe` — portable, ไม่ต้องลง Python, ดับเบิลคลิกใช้ได้เลย
- **macOS:** `INKCOPY.dmg` — ดับเบิลคลิกแล้วลาก `INKCOPY.app` ไปที่ Applications

**สำหรับ macOS** ครั้งแรกที่เปิด ระบบจะถามสิทธิ์ Accessibility — เปิดที่ `System Settings → Privacy & Security → Accessibility` แล้วเปิดสวิตช์ของ INKCOPY (จำเป็นสำหรับการดักจับ Cmd+V และ F9/F10/F12)

- **Config** เซฟอัตโนมัติที่ `%APPDATA%\INKCOPY\config.json` (Windows) / `~/Library/Application Support/INKCOPY/config.json` (macOS)
- **Auto-update** เปิดแอปแล้วถ้ามีเวอร์ชันใหม่บน GitHub Releases ปุ่ม `⬆ vX.X.X` สีเขียวจะโผล่มุมบน คลิกเปิดหน้าโหลด

## ฟีเจอร์หลัก

### 3 โหมดการทำงาน

**📋 Paste Mode (โหมดวาง)**
- อ่านไฟล์ Prompt + Chapter จากโฟลเดอร์
- รวมเนื้อหาแล้ววางลงคลิปบอร์ด
- กด `Ctrl+V` เพื่อไปยังไฟล์ถัดไปอัตโนมัติ
- รองรับการวางหลายไฟล์พร้อมกัน (Concurrent chapters)

**📝 Copy Mode (โหมดคัดลอก)**
- รอรับข้อความจากคลิปบอร์ด
- เมื่อคัดลอกข้อความ จะบันทึกลงไฟล์ Chapter ในโฟลเดอร์ Output อัตโนมัติ
- สามารถเลือกใส่ชื่อไฟล์+บรรทัดว่าง หรือเฉพาะเนื้อหาได้
- กด `Ctrl+C` แล้วโปรแกรมจะบันทึกและไปยังไฟล์ถัดไป

**📖 Vocab Mode (โหมดคำศัพท์)**
- รวบรวมคำศัพท์หรือข้อมูลจากคลิปบอร์ด
- บันทึกลงไฟล์ `vocab.txt` แบบต่อท้าย
- ใช้สำหรับสะสมคำศัพท์ ข้อมูล หรือ reference

### ฮอตคีย์

- **F9**: ไปยังไฟล์ก่อนหน้า
- **F10**: ไปยังไฟล์ถัดไป
- **F12**: หยุด/ทำงานต่อ (Pause/Resume)
- **Ctrl+V** (Windows) / **Cmd+V** (macOS): Paste Mode — วางข้อความแล้วไปต่อ
- **Ctrl+C** (Windows) / **Cmd+C** (macOS): Copy Mode — บันทึกข้อความแล้วไปต่อ

## โครงสร้างโปรแกรม

### ไฟล์หลัก

```
inkcopy/
├── inkcopy.py        # ไฟล์หลักที่รวม logic ทั้งหมด
├── INKCOPY.spec              # PyInstaller spec (สำหรับ build .exe)
├── requirements.txt          # รายการ Python packages
├── README.md                 # ไฟล์นี้
├── assets/
│   ├── inkcopy.png           # โลโก้ต้นฉบับ (512x512)
│   └── inkcopy.ico           # icon ที่ฝังลงใน .exe + ใช้ใน Qt window
├── docs/
│   ├── LOGIC.md              # เอกสาร logic ละเอียด
│   └── config.example.json   # ตัวอย่างการตั้งค่าเปล่า
├── scripts/
│   ├── install.bat           # Windows: pip install -r requirements.txt
│   ├── run.bat               # Windows: รันโปรแกรมจาก source
│   ├── build.bat             # Windows: build INKCOPY.exe
│   ├── install.sh            # macOS/Linux: pip install -r requirements.txt
│   ├── run.sh                # macOS/Linux: รันโปรแกรมจาก source
│   ├── build.sh              # macOS: build INKCOPY.app
│   └── build_icns.sh         # macOS: สร้าง .icns จาก inkcopy.png
└── .github/workflows/
    └── release.yml           # CI: tag push -> build .exe + .dmg แล้ว publish Release อัตโนมัติ
```

Config จริงของผู้ใช้ (`config.json`) ไม่อยู่ใน repo — เซฟไปที่ `%APPDATA%\INKCOPY\config.json` (Windows) / `~/.config/INKCOPY/config.json` (Linux) / `~/Library/Application Support/INKCOPY/config.json` (macOS)

### สถาปัตยกรรมโค้ด

โปรแกรมใช้ PyQt6 สำหรับ UI และ hotkey backend แยกตาม OS — `keyboard` บน Windows, `pynput` บน macOS/Linux:

```python
# ส่วนประกอบหลัก
- SmartClipboardOverlay (หน้าต่างหลัก)
- HotkeySignals (ส่งสัญญาณระหว่าง thread)
- _HotkeyBackend (abstraction: register/unregister/send_paste/is_paste_modifier_held)
    - _KeyboardLibBackend  (Windows: keyboard library)
    - _PynputBackend       (macOS/Linux: pynput)
- Config helpers (จัดการการตั้งค่า)
- Shortcut resolution (จัดการ .lnk บน Windows)
```

## Logic การทำงาน

### 1. การเริ่มต้นโปรแกรม

```python
# ตรวจสอบ dependencies
check_modules()

# สร้างหน้าต่างหลัก
overlay = SmartClipboardOverlay()

# โหลด config ครั้งล่าสุด
overlay._load_saved_config()

# ลงทะเบียนฮอตคีย์
overlay._register_hotkeys()
```

### 2. Paste Mode Logic

```
1. สแกนโฟลเดอร์ Prompt และ Chapter
2. อ่านไฟล์ตามจำนวน concurrent chapters
3. รวมเนื้อหา (Prompt + Chapter)
4. วางลงคลิปบอร์ด
5. รอ Ctrl+V จากผู้ใช้
6. เมื่อได้รับสัญญาณ -> ไปยังไฟล์ถัดไป
```

### 3. Copy Mode Logic

```
1. เริ่ม monitoring คลิปบอร์ด
2. รอการเปลี่ยนแปลงข้อความ
3. เมื่อคลิปบอร์ดเปลี่ยน:
   - อ่านข้อความใหม่
   - สร้างเนื้อหา (ตาม template หรือเฉพาะข้อความ)
   - บันทึกลงไฟล์ในโฟลเดอร์ Output
   - ไปยังไฟล์ถัดไป
```

### 4. การจัดการ Config

```python
# โหลด config
def _load_saved_config():
    cfg = load_config()
    self.prompt_folder = cfg.get("prompt_folder")
    self.chapter_folder = cfg.get("chapter_folder")
    # ... โหลดค่าอื่นๆ

# บันทึก config
def _save_config():
    save_config({
        "prompt_folder": self.prompt_folder,
        "chapter_folder": self.chapter_folder,
        # ... ค่าอื่นๆ
    })
```

## การติดตั้งและรัน

### ทางง่าย: โหลดไฟล์สำเร็จ

- **Windows:** โหลด `INKCOPY.exe` จาก [Releases](https://github.com/snibzyz/inkcopy/releases/latest) → ดับเบิลคลิก
- **macOS:** โหลด `INKCOPY.dmg` → ลาก `INKCOPY.app` ไป `/Applications` → เปิดครั้งแรก กด "Open Anyway" ใน System Settings → Privacy & Security → ให้สิทธิ์ Accessibility

### ทาง dev: รันจาก source

**Windows:**

1. ติดตั้ง [Python 3](https://www.python.org/downloads/) แล้วเปิดตัวเลือกให้ Python อยู่ใน PATH
2. ดับเบิลคลิก **`scripts\install.bat`** ครั้งแรก — รัน `pip install -r requirements.txt`
3. ดับเบิลคลิก **`scripts\run.bat`** เพื่อเปิดโปรแกรม

**macOS / Linux:**

1. ติดตั้ง Python 3 (`brew install python` บน macOS หรือ [python.org](https://www.python.org/downloads/))
2. รัน `bash scripts/install.sh` — รัน `pip install -r requirements.txt`
3. รัน `bash scripts/run.sh` เพื่อเปิดโปรแกรม
4. (macOS) เปิด `System Settings → Privacy & Security → Accessibility` แล้วเปิดสิทธิ์ให้ Terminal/iTerm/Python — จำเป็นเพื่อจับฮอตคีย์ทั่วระบบ

### Build เอง

- **Windows:** ดับเบิลคลิก **`scripts\build.bat`** → ได้ `dist\INKCOPY.exe`
- **macOS:** รัน `bash scripts/build.sh` → ได้ `dist/INKCOPY.app`

### ปล่อย Release ใหม่ (สำหรับ maintainer)

1. แก้ `__version__` ใน `inkcopy.py`
2. `git commit -am "Release v0.X.0" && git push`
3. `git tag v0.X.0 && git push --tags`
4. GitHub Actions จะ build ทั้ง Windows + macOS แล้วสร้าง Release พร้อม `INKCOPY.exe` + `INKCOPY.dmg` อัตโนมัติ
5. ผู้ใช้เวอร์ชันเก่าจะเห็นปุ่ม `⬆ vX.X.X` ในแอปเอง

## การตั้งค่าเริ่มต้น

1. **เลือกโฟลเดอร์ Prompt** - โฟลเดอร์ที่เก็บไฟล์ prompt (.txt, .md)
2. **เลือกโฟลเดอร์ Chapter** - โฟลเดอร์ที่เก็บไฟล์ chapter (.txt, .md)
3. **เลือกโฟลเดอร์ Output** - โฟลเดอร์สำหรับบันทึกไฟล์ (Copy/Vocab mode)

## การปรับแต่ง

### การเปลี่ยนฮอตคีย์

แก้ไขใน `_register_hotkeys()` หรือใน `_HotkeyBackend` impl ของแต่ละ OS:

```python
_hotkey_backend.register(
    on_paste=self._kb_paste_handler,
    on_prev=lambda: self.signals.prev_chapter.emit(),     # F9
    on_next=lambda: self.signals.next_chapter.emit(),     # F10
    on_pause=lambda: self.signals.toggle_pause.emit(),    # F12
)
```

### การปรับ UI Style

แก้ไขใน `_apply_styles()` - ใช้ CSS-like syntax ของ PyQt6

### การเพิ่มโหมดใหม่

1. เพิ่มค่าคงที่ใน `MODE_*`
2. เพิ่ม logic ใน `_toggle_mode()`
3. เพิ่ม handler ใน `_on_clipboard_changed()`

## การแก้ไขปัญหา

### ปัญหาที่พบบ่อย

**ฮอตคีย์ไม่ทำงาน**
- Windows: ตรวจสอบว่าติดตั้ง `keyboard` แล้ว, บางโปรแกรมอาจ block ฮอตคีย์ (ลองรันเป็น admin)
- macOS: ต้องให้สิทธิ์ Accessibility — `System Settings → Privacy & Security → Accessibility` แล้วเปิดสวิตช์ของ INKCOPY (หรือ Terminal ถ้ารันจาก source). ถ้าเพิ่งให้สิทธิ์ ต้องปิด-เปิดแอปใหม่
- Linux: ต้องติดตั้ง `pynput` และอาจต้องสิทธิ์ X11/Wayland เพิ่มเติม

**คลิปบอร์ดไม่ตอบสนอง**
- บน Windows อาจต้องระยะเวลาสักครู่ให้คลิปบอร์ดอัปเดต
- โปรแกรมใช้ delayed check 120ms เพื่อแก้ปัญหานี้

**ไฟล์ .lnk ไม่ทำงาน**
- ตรวจสอบว่า PowerShell สามารถรันได้
- .lnk resolution ใช้ PowerShell COM object

## License

สามารถนำไปพัฒนาต่อได้ตามต้องการ

## ผู้พัฒนา

สร้างขึ้นสำหรับการเขียนนิยายและจัดการเนื้อหาแบบอัตโนมัติ
