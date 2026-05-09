# Smart Clipboard - Logic การทำงานฉบับละเอียด

เอกสารนี้อธิบาย logic การทำงานของโปรแกรม Smart Clipboard ในระดับละเอียดสำหรับผู้ที่ต้องการแกะโค้ดหรือพัฒนาต่อ

**Repo:** [snibzyz/smartc](https://github.com/snibzyz/smartc) — การตั้งค่าเก็บที่ `config.json` ข้าง `smart_clipboard.py` (ดู `config.example.json` ใน repo; ไฟล์จริงไม่ commit)

## 1. สถาปัตยกรรมโดยรวม

```
┌─────────────────────────────────────────────────────────────┐
│                    SmartClipboardOverlay                   │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │   UI Layer  │  │ Config Layer │  │  Business Logic │  │
│  │             │  │              │  │                 │  │
│  │ - Widgets   │  │ - JSON       │  │ - Mode Switch   │  │
│  │ - Styles    │  │ - Save/Load  │  │ - File Handling │  │
│  │ - Events    │  │ - Defaults   │  │ - Clipboard     │  │
│  └─────────────┘  └──────────────┘  └─────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              Signal Bridge (HotkeySignals)             │ │
│  │  - paste_detected    - clipboard_changed               │ │
│  │  - prev_chapter      - next_chapter                    │ │
│  │  - toggle_pause                                       │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## 2. การเริ่มต้นโปรแกรม (Initialization Flow)

```python
# 1. Module Validation
check_modules() → ตรวจสอบ keyboard, natsort, PyQt6

# 2. Main Window Creation
SmartClipboardOverlay.__init__():
    ├─ Set state variables
    ├─ Connect signals
    ├─ Set window flags (frameless, always on top)
    ├─ Build UI (_build_ui)
    ├─ Apply styles (_apply_styles)
    ├─ Load config (_load_saved_config)
    └─ Show window

# 3. Hotkey Registration
_register_hotkeys():
    ├─ keyboard.on_press_key("v", _kb_paste_handler)  # Ctrl+V detection
    ├─ keyboard.add_hotkey("f9", prev_chapter)
    ├─ keyboard.add_hotkey("f10", next_chapter)
    └─ keyboard.add_hotkey("f12", toggle_pause)
```

## 3. UI Structure

### 3.1 Layout Hierarchy

```
QVBoxLayout (root)
├─ Title Row (QHBoxLayout)
│   ├─ Title Label
│   ├─ Minimize Button
│   └─ Close Button
├─ Mode Button
├─ Status Label
├─ Content Widget
│   ├─ Prompt Folder Row
│   ├─ Chapter Folder Row
│   ├─ Output Folder Row
│   ├─ Concurrent Chapters Row
│   ├─ Content Start Line Row
│   ├─ Copy Template Checkbox
│   ├─ Prompt/Chapter Checkboxes
│   ├─ Fetch Button
│   ├─ Hotkey Legend
│   └─ Control Buttons Row
└─ (เนื้อหาอื่นๆ)
```

### 3.2 State Variables ที่สำคัญ

```python
# Folder/File Management
self.prompt_folder: str | None
self.chapter_folder: str | None
self.output_folder: str | None
self.prompt_files: list[tuple[str, str]]
self.chapter_files: list[tuple[str, str]]

# Mode & Navigation
self.mode: str  # MODE_PASTE, MODE_COPY, MODE_VOCAB
self.current_index: int
self.paused: bool

# Copy Mode Settings
self.content_start_line: int  # บรรทัดที่วางเนื้อหา
self.copy_template_enabled: bool  # ใส่ชื่อไฟล์+บรรทัดว่างหรือไม่

# Paste Mode Settings
self.concurrent_chapters: int  # จำนวนไฟล์ต่อการวาง
self.include_prompt: bool
self.include_chapter: bool
```

## 4. Mode Logic รายละเอียด

### 4.1 Paste Mode Flow

```python
def _load_clipboard_paste_mode():
    """
    สร้างเนื้อหาสำหรับวางลงคลิปบอร์ด
    """
    # 1. รวบรวมไฟล์ตามจำนวน concurrent
    files_to_process = self.chapter_files[
        self.current_index : self.current_index + self.concurrent_chapters
    ]
    
    # 2. สร้างเนื้อหาแบบมี prompt
    if self.include_prompt and self.prompt_files:
        # เพิ่ม prompt ที่จุดเริ่มต้น
        content = prompt_content + "\n\n" + chapter_content
    
    # 3. สร้างเนื้อหาแบบไม่มี prompt
    else:
        # เฉพาะ chapter content
    
    # 4. วางลงคลิปบอร์ด
    clipboard = QApplication.clipboard()
    clipboard.setText(content)
    
    # 5. อัปเดต status
    self.status_label.setText(f"[READY] {count} chapters loaded")
```

### 4.2 Copy Mode Flow

```python
def _on_copy_clipboard_changed():
    """
    จัดการการเปลี่ยนแปลงคลิปบอร์ดใน Copy mode
    """
    # 1. Validation
    if not self.chapter_files or not self.output_folder:
        return
    
    # 2. Get current chapter
    ch_name = self.chapter_files[self.current_index][0]
    ch_title = Path(ch_name).stem
    
    # 3. Build content based on template setting
    if self.copy_template_enabled:
        # Template mode: ชื่อไฟล์ + บรรทัดว่าง + เนื้อหา
        blank_lines = max(0, self.content_start_line - 1)
        content = f"{ch_title}" + "\n" * blank_lines + f"{text}\n"
    else:
        # Plain mode: เฉพาะเนื้อหา
        content = f"{text}\n"
    
    # 4. Save to file
    out_path = os.path.join(self.output_folder, ch_name)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    # 5. Advance to next chapter
    if self.current_index < len(self.chapter_files) - 1:
        self.current_index += 1
    else:
        self.status_label.setText("[DONE] All chapters saved")
```

### 4.3 Vocab Mode Flow

```python
def _on_vocab_clipboard_changed():
    """
    สะสมข้อความลง vocab.txt
    """
    # 1. Validation
    if not self.vocab_file_path:
        return
    
    # 2. Append with separator
    with open(self.vocab_file_path, "a", encoding="utf-8") as f:
        if self.vocab_entry_count > 0:
            f.write("\n\n")  # คั่นด้วยบรรทัดว่าง 2 บรรทัด
        f.write(text.strip())
    
    # 3. Update counter
    self.vocab_entry_count += 1
```

## 5. Signal System

### 5.1 Signal Bridge Architecture

```python
class HotkeySignals(QObject):
    # สัญญาณสำหรับสื่อสารระหว่าง threads
    paste_detected = pyqtSignal()
    clipboard_changed = pyqtSignal()
    prev_chapter = pyqtSignal()
    next_chapter = pyqtSignal()
    toggle_pause = pyqtSignal()
```

### 5.2 Signal Flow Diagram

```
Keyboard Input → Hotkey Handler → Signal.emit() → Slot Method → UI Update

Ctrl+V → _kb_paste_handler → paste_detected.emit() → _on_paste() → Next chapter
F9     → lambda → prev_chapter.emit() → _go_prev() → Previous chapter
F10    → lambda → next_chapter.emit() → _go_next() → Next chapter
F12    → lambda → toggle_pause.emit() → _toggle_pause() → Pause/Resume
```

## 6. Clipboard Management

### 6.1 Clipboard Monitor (Copy/Vocab Mode)

```python
def _clipboard_data_changed():
    """
    จัดการปัญหา Windows clipboard timing
    """
    # Windows มีปัญหา: clipboard ไม่พร้อมใช้งานทันทีเมื่อ dataChanged ไฟร์
    # ใช้ QTimer เพื่อ delay 120ms ให้ clipboard พร้อม
    self._clipboard_check_timer = QTimer(self)
    self._clipboard_check_timer.setSingleShot(True)
    self._clipboard_check_timer.timeout.connect(self._clipboard_check_deferred)
    self._clipboard_check_timer.start(120)
```

### 6.2 Clipboard Write (Paste Mode)

```python
def _load_clipboard_paste_mode():
    """
    เขียนข้อมูลลง clipboard พร้อม ignore การเปลี่ยนแปลงชั่วคราว
    """
    self._ignore_clipboard_change = True  # ป้องกัน trigger ตัวเอง
    clipboard.setText(content)
    self._ignore_clipboard_change = False
```

## 7. File System Operations

### 7.1 Shortcut Resolution (.lnk)

```python
def _resolve_shortcut(path: str) -> str | None:
    """
    แกะ .lnk file บน Windows ผ่าน PowerShell
    """
    # ใช้ WScript.Shell COM object ผ่าน PowerShell
    result = subprocess.run([
        "powershell", "-NoProfile", "-NonInteractive", "-Command",
        "$p = $env:_LNK_PATH; $sh = New-Object -ComObject WScript.Shell; "
        "$sc = $sh.CreateShortcut($p); Write-Output $sc.TargetPath"
    ], env={"_LNK_PATH": path}, capture_output=True)
    
    return result.stdout.strip() if result.returncode == 0 else None
```

### 7.2 File Scanning Logic

```python
def _scan_chapter_folder(self):
    """
    สแกนโฟลเดอร์และจัดเรียงไฟล์ตามลำดับธรรมชาติ
    """
    # 1. กรองไฟล์ที่รองรับ
    files = [f for f in os.listdir(base) 
            if f.lower().endswith(('.txt', '.md', '.lnk'))]
    
    # 2. จัดเรียงตามลำดับธรรมชาติ (natsort)
    for f in natsort.natsorted(files):
        # 3. Resolve .lnk ถ้ามี
        path = _resolve_path_maybe_shortcut(base, f)
        entries.append((f, path))
    
    self.chapter_files = entries
```

## 8. Configuration Management

### 8.1 Config Schema

```json
{
  "prompt_folder": "path/to/prompts",
  "chapter_folder": "path/to/chapters", 
  "output_folder": "path/to/output",
  "content_start_line": 3,
  "concurrent_chapters": 1,
  "include_prompt": true,
  "include_chapter": true,
  "copy_template_enabled": true
}
```

### 8.2 Config Load/Save Pattern

```python
def _load_saved_config(self):
    cfg = load_config()
    
    # โหลดค่าแบบมี fallback
    self.content_start_line = cfg.get("content_start_line", 3)
    
    # โหลดโฟลเดอร์แบบมี shortcut resolution
    if cfg.get("chapter_folder"):
        cf = cfg["chapter_folder"]
        if cf.lower().endswith(".lnk"):
            resolved = _resolve_shortcut(cf)
            # ... จัดการ resolved path

def _save_config(self):
    save_config({
        "prompt_folder": self.prompt_folder or "",
        "chapter_folder": self.chapter_folder or "",
        # ... บันทึกค่าทั้งหมด
    })
```

## 9. Error Handling Patterns

### 9.1 Module Validation

```python
def check_modules():
    missing = []
    try:
        import keyboard
    except ImportError:
        missing.append("keyboard")
    
    if missing:
        # แสดงข้อความ error และคำแนะนำการติดตั้ง
        print("ERROR: Missing required Python modules!")
        sys.exit(1)
```

### 9.2 Clipboard Error Handling

```python
def _stop_clipboard_monitor(self):
    try:
        clipboard = QApplication.clipboard()
        clipboard.dataChanged.disconnect(self._clipboard_data_changed)
    except TypeError:
        # กรณีที่ไม่เคย connect มาก่อน
        pass
```

## 10. Performance Considerations

### 10.1 Timer-based Operations

```python
# Clipboard check delay (Windows timing issue)
self._clipboard_check_timer.start(120)

# Status update delay
QTimer.singleShot(1500, self._update_status)
```

### 10.2 File I/O Optimization

```python
# ใช้ with statement สำหรับ file operations
with open(out_path, "w", encoding="utf-8") as f:
    f.write(content)

# ใช้ natsort สำหรับการจัดเรียงไฟล์
for f in natsort.natsorted(files):
    # ... process files
```

## 11. Extensibility Points

### 11.1 การเพิ่ม Mode ใหม่

```python
# 1. เพิ่มค่าคงที่
MODE_NEW = "new"

# 2. แก้ _toggle_mode()
elif self.mode == self.MODE_COPY:
    self.mode = self.MODE_NEW
    # ... setup new mode

# 3. เพิ่ม handler ใน _on_clipboard_changed()
elif self.mode == self.MODE_NEW:
    self._on_new_mode_clipboard_changed()
```

### 11.2 การเพิ่ม Config Option

```python
# 1. เพิ่ม state variable
self.new_setting: bool = True

# 2. เพิ่ม UI element
self.new_checkbox = QCheckBox("New Setting")

# 3. เพิ่มใน config
self.new_setting = cfg.get("new_setting", True)

# 4. เพิ่มใน save_config
"new_setting": self.new_setting,
```

## 12. Debugging Tips

### 12.1 Logging Pattern

```python
# เพิ่ม print statements สำหรับ debugging
print(f"[DEBUG] Mode changed to: {self.mode}")
print(f"[DEBUG] Current index: {self.current_index}")
print(f"[DEBUG] Chapter files: {len(self.chapter_files)}")
```

### 12.2 Common Issues

1. **Hotkey not working**: Check keyboard library installation and permissions
2. **Clipboard timing**: Windows delay issue - use deferred check
3. **File permissions**: Ensure write access to output folder
4. **Encoding issues**: Always use UTF-8 encoding for file operations

---

เอกสารนี้ครอบคลุม logic การทำงานของ Smart Clipboard ในระดับละเอียด สำหรับผู้ที่ต้องการศึกษาโครงสร้างโค้ดหรือพัฒนาต่อ
