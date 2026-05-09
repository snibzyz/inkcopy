# Smart Clipboard (SmartC)

โปรแกรมคลิปบอร์ดอัจฉริยะสำหรับนักเขียน สร้างขึ้นมาเพื่อช่วยในการจัดการไฟล์ Prompt และ Chapter ในการเขียนนิยาย/เนื้อหาแบบอัตโนมัติ

**Repository:** [https://github.com/snibzyz/smartc](https://github.com/snibzyz/smartc)

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
- **Ctrl+V**: Paste Mode - วางข้อความแล้วไปต่อ
- **Ctrl+C**: Copy Mode - บันทึกข้อความแล้วไปต่อ

## โครงสร้างโปรแกรม

### ไฟล์หลัก

```
SmartC/
├── smart_clipboard.py   # ไฟล์หลักที่รวม logic ทั้งหมด
├── config.json          # การตั้งค่า (สร้างเอง — ไม่ commit; ดู config.example.json)
├── config.example.json  # ตัวอย่างการตั้งค่าเปล่า สำหรับ clone ใหม่
├── requirements.txt     # รายการ package
├── install.bat          # ครั้งแรก: pip install -r requirements.txt
├── run.bat              # รันโปรแกรม
├── LOGIC.md             # เอกสาร logic ละเอียด
└── README.md            # ไฟล์นี้
```

### สถาปัตยกรรมโค้ด

โปรแกรมใช้ PyQt6 สำหรับ UI และ keyboard library สำหรับฮอตคีย์:

```python
# ส่วนประกอบหลัก
- SmartClipboardOverlay (หน้าต่างหลัก)
- HotkeySignals (ส่งสัญญาณระหว่าง thread)
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

### Windows

1. ติดตั้ง [Python 3](https://www.python.org/downloads/) แล้วเปิดตัวเลือกให้ Python อยู่ใน PATH
2. ดับเบิลคลิก **`install.bat`** ครั้งแรก (หรือเมื่อเปลี่ยนเครื่อง) — รัน `pip install -r requirements.txt` ธรรมดา ไม่มี venv
3. ดับเบิลคลิก **`run.bat`** เพื่อเปิดโปรแกรม

**การตั้งค่า:** คัดลอก `config.example.json` เป็น `config.json` ได้ถ้าต้องการ — หรือตั้งค่าใน UI; `config.json` ไม่ถูก commit ขึ้น git

### Linux / macOS

```bash
pip install -r requirements.txt
python3 smart_clipboard.py
```

(ฮอตคีย์ `keyboard` อาจต้องรันด้วยสิทธิ์ที่เหมาะสมตามระบบ)

## การตั้งค่าเริ่มต้น

1. **เลือกโฟลเดอร์ Prompt** - โฟลเดอร์ที่เก็บไฟล์ prompt (.txt, .md)
2. **เลือกโฟลเดอร์ Chapter** - โฟลเดอร์ที่เก็บไฟล์ chapter (.txt, .md)
3. **เลือกโฟลเดอร์ Output** - โฟลเดอร์สำหรับบันทึกไฟล์ (Copy/Vocab mode)

## การปรับแต่ง

### การเปลี่ยนฮอตคีย์

แก้ไขใน `_register_hotkeys()`:

```python
keyboard.add_hotkey("f9", lambda: self.signals.prev_chapter.emit())
keyboard.add_hotkey("f10", lambda: self.signals.next_chapter.emit())
keyboard.add_hotkey("f12", lambda: self.signals.toggle_pause.emit())
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
- ตรวจสอบว่าติดตั้ง keyboard library แล้ว
- บางโปรแกรมอาจ block ฮอตคีย์ (พยายามรันเป็น admin)

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
