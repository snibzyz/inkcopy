import sys
import os

# Check for required modules before importing
def check_modules():
    missing = []
    try:
        import keyboard
    except ImportError:
        missing.append("keyboard")
    try:
        import natsort
    except ImportError:
        missing.append("natsort")
    try:
        from PyQt6.QtCore import Qt, QUrl, QMimeData, QTimer, pyqtSignal, QObject
    except ImportError:
        missing.append("PyQt6")
    
    if missing:
        print("=" * 60)
        print("ERROR: Missing required Python modules!")
        print("=" * 60)
        print(f"\nMissing: {', '.join(missing)}")
        print("\nTo fix, run this command in terminal:")
        print(f"   pip install -r {os.path.dirname(os.path.abspath(__file__))}\\requirements.txt")
        print("\nOr install manually:")
        print("   pip install keyboard natsort PyQt6")
        print("\nPress Enter to exit...")
        input()
        sys.exit(1)

check_modules()

import json
import re
import unicodedata
from pathlib import Path

import keyboard
import natsort
from PyQt6.QtCore import Qt, QUrl, QMimeData, QTimer, pyqtSignal, QObject, QEvent
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QGraphicsOpacityEffect, QCheckBox,
    QScrollArea, QRadioButton, QButtonGroup, QSizePolicy, QFrame,
    QLineEdit,
)
from PyQt6.QtGui import QFont, QIntValidator

__version__ = "0.1.1"
UPDATE_REPO = "snibzyz/inkcopy"


def _is_newer_version(remote_tag: str, current: str) -> bool:
    def _parts(s: str):
        s = s.lstrip("vV").strip()
        out = []
        for p in s.split("."):
            digits = "".join(c for c in p if c.isdigit())
            out.append(int(digits) if digits else 0)
        return tuple(out)
    try:
        return _parts(remote_tag) > _parts(current)
    except Exception:
        return False


def _config_dir() -> str:
    # Per-user config directory: %APPDATA%\INKCOPY on Windows, XDG/Library equivalents elsewhere.
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "INKCOPY")


def _legacy_config_path() -> str:
    # Old location (next to .exe or script) — kept only for one-time migration into _config_dir().
    if getattr(sys, "frozen", False):
        base = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "config.json")


def _resource_path(rel: str) -> str:
    # Bundled resources live in sys._MEIPASS when frozen, beside the script in dev.
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, rel)


CONFIG_DIR = _config_dir()
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
ICON_PATH = _resource_path("inkcopy.ico")


# ---------------------------------------------------------------------------
# Shortcut (.lnk) resolution (Windows)
# ---------------------------------------------------------------------------
_LNK_CACHE: dict[str, str | None] = {}


def _subprocess_no_window_kwargs() -> dict:
    # Suppress the console window flash when spawning helper processes from a
    # PyInstaller --windowed build. No-op on non-Windows.
    if sys.platform != "win32":
        return {}
    import subprocess
    CREATE_NO_WINDOW = 0x08000000
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0  # SW_HIDE
    return {"creationflags": CREATE_NO_WINDOW, "startupinfo": si}


def _resolve_shortcut(path: str) -> str | None:
    """Resolve a Windows .lnk shortcut to its target path. Returns None on non-Windows or failure."""
    if sys.platform != "win32":
        return None
    path = os.path.abspath(path)
    if not path.lower().endswith(".lnk"):
        return None
    cache_key = path.casefold()
    if cache_key in _LNK_CACHE:
        return _LNK_CACHE[cache_key]
    try:
        import subprocess
        env = os.environ.copy()
        env["_LNK_PATH"] = path
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "$p = $env:_LNK_PATH; $sh = New-Object -ComObject WScript.Shell; $sc = $sh.CreateShortcut($p); Write-Output $sc.TargetPath",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            env=env,
            **_subprocess_no_window_kwargs(),
        )
        if result.returncode == 0 and result.stdout:
            target = result.stdout.strip()
            if target:
                _LNK_CACHE[cache_key] = target
                return target
    except Exception:
        pass
    _LNK_CACHE[cache_key] = None
    return None


def _resolve_path_maybe_shortcut(base_folder: str, name: str) -> str:
    """Return the path to use for a file; if name is a .lnk, return resolved target path."""
    full = os.path.join(base_folder, name)
    if name.lower().endswith(".lnk"):
        resolved = _resolve_shortcut(full)
        if resolved and (os.path.isfile(resolved) or os.path.isdir(resolved)):
            return resolved
    return full


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------
def load_config() -> dict:
    if not os.path.isfile(CONFIG_PATH):
        # One-time silent migration from legacy location next to executable/script.
        legacy = _legacy_config_path()
        if os.path.isfile(legacy):
            try:
                import shutil
                os.makedirs(CONFIG_DIR, exist_ok=True)
                shutil.copy2(legacy, CONFIG_PATH)
                try:
                    os.remove(legacy)
                except OSError:
                    pass
            except Exception:
                pass
    if os.path.isfile(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(data: dict):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _clean_chapter_stem(stem: str) -> str:
    """NFC, trim, strip BOM for stable parsing."""
    s = unicodedata.normalize("NFC", stem)
    return s.strip().strip("\ufeff")


def _canonical_prefix_key(prefix: str) -> str:
    """Compare prefixes ignoring outer space, internal whitespace runs, Latin case."""
    s = unicodedata.normalize("NFC", prefix)
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    return s.casefold()


def _is_ascii_digit_run(s: str) -> bool:
    return bool(s) and all("0" <= c <= "9" for c in s)


def _split_stem_trailing_digits(stem: str) -> tuple[str, str] | None:
    """
    Split stem into (prefix, trailing_ascii_digits).
    Tries cleaned stem then a rstrip of common trailing punctuation so
    'Episode_007.' / 'Episode_007' still match.
    """
    s = _clean_chapter_stem(stem)
    if not s:
        return None
    candidates: list[str] = [s]
    stripped = s.rstrip(" \t._-—：:=＆&）)】]")
    if stripped != s:
        candidates.append(stripped)
    seen: set[str] = set()
    for cand in candidates:
        if not cand or cand in seen:
            continue
        seen.add(cand)
        m = re.search(r"(\d+)$", cand)
        if not m:
            continue
        digits = m.group(1)
        if not _is_ascii_digit_run(digits):
            continue
        return cand[: m.start(1)], digits
    return None


def _detect_chapter_number(name: str) -> int | None:
    """Extract the auto-detected chapter number from a filename's trailing digits.
    Works for any width: '7.txt' -> 7, '011.txt' -> 11, 'Title 1234.txt' -> 1234."""
    stem = Path(name).stem
    result = _split_stem_trailing_digits(stem)
    if not result:
        return None
    try:
        return int(result[1])
    except (ValueError, TypeError):
        return None


def copy_mode_group_output_name(first_ch_name: str, last_ch_name: str) -> tuple[str, str]:
    """
    Output filename + title stem for one Copy-mode save covering a chapter range.
    Auto-detects a shared text prefix and trailing decimal block per stem; any
    padding width is preserved via zfill(max(len(n0), len(n1))).
    Falls back to the first chapter's filename if no safe range can be formed.
    """
    p0 = Path(first_ch_name)
    p1 = Path(last_ch_name)
    ext = p0.suffix
    s0, s1 = p0.stem, p1.stem
    c0, c1 = _clean_chapter_stem(s0), _clean_chapter_stem(s1)
    if c0 == c1:
        return first_ch_name, s0
    a0 = _split_stem_trailing_digits(s0)
    a1 = _split_stem_trailing_digits(s1)
    if not a0 or not a1:
        return first_ch_name, s0
    if _canonical_prefix_key(a0[0]) != _canonical_prefix_key(a1[0]):
        return first_ch_name, s0
    n0s, n1s = a0[1], a1[1]
    try:
        n0, n1 = int(n0s), int(n1s)
    except ValueError:
        return first_ch_name, s0
    width = max(len(n0s), len(n1s))
    left = str(n0).zfill(width)
    right = str(n1).zfill(width)
    out_prefix = a0[0]
    stem_out = f"{out_prefix}{left}-{right}"
    return f"{stem_out}{ext}", stem_out


# ---------------------------------------------------------------------------
# Windows: SendInput (Ctrl+V) สำหรับวางไฟล์/ข้อความสังเคราะห์หลังผู้ใช้ Ctrl+V รอบแรก
# ---------------------------------------------------------------------------
def _win32_set_clipboard_unicode(text: str) -> bool:
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32

    opened = False
    for _ in range(40):
        if user32.OpenClipboard(None):
            opened = True
            break
        kernel32.Sleep(25)
    if not opened:
        return False
    try:
        if not user32.EmptyClipboard():
            return False
        raw = (text + "\0").encode("utf-16-le")
        sz = len(raw)
        h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, sz)
        if not h_mem:
            return False
        ptr = kernel32.GlobalLock(h_mem)
        if not ptr:
            kernel32.GlobalFree(h_mem)
            return False
        try:
            ctypes.memmove(ptr, raw, sz)
        finally:
            kernel32.GlobalUnlock(h_mem)
        if not user32.SetClipboardData(CF_UNICODETEXT, h_mem):
            kernel32.GlobalFree(h_mem)
            return False
        return True
    finally:
        user32.CloseClipboard()


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
    _INPUT_KEYBOARD = 1
    _KEYEVENTF_KEYUP = 0x0002

    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = (
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", _ULONG_PTR),
        )

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = (
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", _ULONG_PTR),
        )

    class _HARDWAREINPUT(ctypes.Structure):
        _fields_ = (
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        )

    class _INPUT_U(ctypes.Union):
        _fields_ = (("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT))

    class _WININPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = (("type", wintypes.DWORD), ("u", _INPUT_U))

    def _win32_sendinput_ctrl_v() -> bool:
        def _kin(vk: int, flags: int = 0) -> _WININPUT:
            i = _WININPUT()
            i.type = _INPUT_KEYBOARD
            i.ki = _KEYBDINPUT(vk, 0, flags, 0, 0)
            return i

        VK_CONTROL = 0x11
        VK_V = 0x56
        seq = (_WININPUT * 4)(
            _kin(VK_CONTROL, 0),
            _kin(VK_V, 0),
            _kin(VK_V, _KEYEVENTF_KEYUP),
            _kin(VK_CONTROL, _KEYEVENTF_KEYUP),
        )
        n = ctypes.windll.user32.SendInput(4, ctypes.byref(seq), ctypes.sizeof(_WININPUT))
        return n == 4

else:

    def _win32_sendinput_ctrl_v() -> bool:
        return False


# ---------------------------------------------------------------------------
# Signal bridge
# ---------------------------------------------------------------------------
class HotkeySignals(QObject):
    paste_detected = pyqtSignal()
    clipboard_changed = pyqtSignal()
    prev_chapter = pyqtSignal()
    next_chapter = pyqtSignal()
    toggle_pause = pyqtSignal()
    update_available = pyqtSignal(str, str)  # (tag, html_url)


# ---------------------------------------------------------------------------
# Main Overlay Widget
# ---------------------------------------------------------------------------
class SmartClipboardOverlay(QWidget):
    MODE_PASTE = "paste"
    MODE_COPY = "copy"
    MODE_VOCAB = "vocab"
    PROMPT_ROWS_BEFORE_SCROLL = 4
    _paste_hotkey_event_type: QEvent.Type | None = None

    @classmethod
    def _get_paste_hotkey_event_type(cls) -> QEvent.Type:
        if cls._paste_hotkey_event_type is None:
            cls._paste_hotkey_event_type = QEvent.Type(QEvent.registerEventType())
        return cls._paste_hotkey_event_type

    def __init__(self):
        super().__init__()

        # ---- state ----------------------------------------------------------
        self.prompt_folder: str | None = None
        self.prompt_files: list[tuple[str, str]] = []  # (display_name, path_for_url); .lnk resolved
        self.chapter_folder: str | None = None
        self.chapter_files: list[tuple[str, str]] = []  # current view (may be range-filtered)
        self._chapter_files_all: list[tuple[str, str]] = []  # full list before range filter
        self._chapter_idx_by_num: dict[int, int] = {}  # detected chapter num -> index in chapter_files
        self._chapter_range: tuple[int | None, int | None] | None = None  # (lo, hi) when filter active
        self.output_folder: str | None = None
        self.current_index: int = 0
        self.paused: bool = False
        self.hotkeys_registered: bool = False
        self.mode: str = self.MODE_PASTE
        self._ignore_clipboard_change: bool = False
        self._last_clipboard_text: str = ""
        self._clipboard_check_timer: QTimer | None = None  # deferred clipboard read (Copy mode)
        self.content_start_line: int = 3  #  configurable: which line to place content
        self.minimized: bool = False
        self.toast: ToastNotification | None = None
        self.concurrent_chapters: int = 1  # how many chapters to paste at once
        self.vocab_file_path: str | None = None  # resolved full path during a vocab session
        self.vocab_filename: str = "vocab.txt"  # configurable filename, saved across sessions
        self.vocab_entry_count: int = 0  # track number of entries in vocab file
        self.include_prompt: bool = True  # whether to include prompt files in paste mode
        self.include_chapter: bool = True  # whether to include chapter files in paste mode
        self.copy_template_enabled: bool = True  # whether copy mode writes title + blank lines before content
        # Paste mode: per prompt filename -> True = text, False = file URL on clipboard
        self.prompt_paste_modes: dict[str, bool] = {}
        self._legacy_prompt_all_text: bool | None = None  # migrate from prompt_paste_as_text once
        self.chapter_paste_as_text: bool = False  # chapters: single toggle file vs text
        # Mixed file+text: คลิปบอร์ด = ข้อความ → Ctrl+V คุณวาง text → โปรแกรม Ctrl+V ไฟล์ → Ctrl+V ข้อความซ้ำ → สลับตอน
        self._staged_pending_file_paths: list[str] | None = None
        self._staged_plain_text_for_repeat: str | None = None
        self._suppress_paste_hotkey: bool = False
        self._staged_sequence_active: bool = False  # กัน Ctrl+V ซ้ำระหว่างรอ → advance ผิดรอบ
        # หลัง Ctrl+V ของคุณ (โหมดไฟล์+ข้อความ): แชทมักต้องรอก่อนค่อยรับ paste ข้อความ — ปรับได้ใน config.json
        self.staged_ms_after_user_paste = 300
        self.staged_ms_clipboard_to_ctrl_v = 60
        self.staged_ms_after_text_paste = 150
        self.staged_ms_simple_paste = 90

        # ---- signal bridge ---------------------------------------------------
        self.signals = HotkeySignals()
        self.signals.paste_detected.connect(self._on_paste, Qt.ConnectionType.QueuedConnection)
        self._paste_hotkey_timer = QTimer(self)
        self._paste_hotkey_timer.setSingleShot(True)
        self._paste_hotkey_timer.timeout.connect(self.signals.paste_detected.emit)
        self.signals.clipboard_changed.connect(self._on_clipboard_changed)
        self.signals.prev_chapter.connect(self._go_prev)
        self.signals.next_chapter.connect(self._go_next)
        self.signals.toggle_pause.connect(self._toggle_pause)
        self.signals.update_available.connect(self._on_update_available)

        # ---- window flags ----------------------------------------------------
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # ---- dragging support ------------------------------------------------
        self._drag_pos = None

        # ---- build UI -------------------------------------------------------
        self._build_ui()
        self._apply_styles()
        self._apply_mode_visibility()

        # ---- load saved config -----------------------------------------------
        self._load_saved_config()

        # position: top-right corner
        screen = QApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        self.move(screen.width() - self.width() - 24, 24)

        self.show()

        # ---- update check (background, non-blocking) -------------------------
        self._update_url = None
        self._start_update_check()

    # ============================================================ Update check
    def _start_update_check(self):
        import threading

        def _run():
            try:
                import urllib.request
                req = urllib.request.Request(
                    f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest",
                    headers={
                        "Accept": "application/vnd.github+json",
                        "User-Agent": f"INKCOPY/{__version__}",
                    },
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                tag = (data.get("tag_name") or "").strip()
                url = (data.get("html_url") or "").strip()
                if tag and _is_newer_version(tag, __version__):
                    self.signals.update_available.emit(tag, url)
            except Exception:
                pass

        threading.Thread(target=_run, daemon=True).start()

    def _on_update_available(self, tag: str, url: str):
        self._update_url = url
        self.update_btn.setText(f"⬆ {tag}")
        self.update_btn.setToolTip(f"New version {tag} available — click to download")
        self.update_btn.setVisible(True)
        self.adjustSize()

    def _open_update(self):
        if self._update_url:
            import webbrowser
            webbrowser.open(self._update_url)

    # ==================================================================== UI
    def _build_ui(self):
        root = QVBoxLayout()
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(8)

        # -- title row
        title_row = QHBoxLayout()
        self.title_label = QLabel("INKCOPY")
        self.title_label.setObjectName("title")

        self.update_btn = QPushButton("⬆")
        self.update_btn.setObjectName("updateBtn")
        self.update_btn.setVisible(False)
        self.update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_btn.clicked.connect(self._open_update)

        self.minimize_btn = QPushButton("−")
        self.minimize_btn.setObjectName("minimizeBtn")
        self.minimize_btn.setFixedSize(24, 24)
        self.minimize_btn.clicked.connect(self._toggle_minimize)

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("closeBtn")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.clicked.connect(self._quit)
        
        title_row.addWidget(self.title_label)
        title_row.addWidget(self.update_btn)
        title_row.addStretch()
        title_row.addWidget(self.minimize_btn)
        title_row.addWidget(self.close_btn)
        root.addLayout(title_row)

        # -- mode toggle
        mode_row = QHBoxLayout()
        self.mode_btn = QPushButton("📋 [PASTE MODE]  Prompt+Chapter → Clipboard")
        self.mode_btn.setObjectName("modeBtn")
        self.mode_btn.clicked.connect(self._toggle_mode)
        mode_row.addWidget(self.mode_btn)
        root.addLayout(mode_row)

        # -- status
        self.status_label = QLabel("-- Select folders first --")
        self.status_label.setObjectName("status")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        # Container for collapsible content
        self.content_widget = QWidget()
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)

        # -- prompt selector
        prompt_row = QHBoxLayout()
        self.prompt_btn = QPushButton("📁 Prompt Folder")
        self.prompt_btn.setObjectName("actionBtn")
        self.prompt_btn.clicked.connect(self._select_prompt)
        self.prompt_files_btn = QPushButton("📄 Files…")
        self.prompt_files_btn.setObjectName("controlBtn")
        self.prompt_files_btn.setToolTip("เลือกหลายไฟล์ prompt โดยตรง (แทนที่ของเดิม)")
        self.prompt_files_btn.clicked.connect(self._select_prompt_files_picker)
        self.prompt_add_files_btn = QPushButton("➕ เพิ่ม")
        self.prompt_add_files_btn.setObjectName("addBtn")
        self.prompt_add_files_btn.setToolTip("เพิ่มไฟล์ prompt ทีหลัง (ไม่ลบของเดิม)")
        self.prompt_add_files_btn.clicked.connect(self._add_prompt_files_picker)
        self.prompt_info = QLabel("--")
        self.prompt_info.setObjectName("info")
        self.prompt_info.setTextFormat(Qt.TextFormat.RichText)
        prompt_row.addWidget(self.prompt_btn)
        prompt_row.addWidget(self.prompt_files_btn)
        prompt_row.addWidget(self.prompt_add_files_btn)
        prompt_row.addWidget(self.prompt_info, 1)
        self._row_prompt = QWidget()
        self._row_prompt.setLayout(prompt_row)
        content_layout.addWidget(self._row_prompt)

        prompt_list_caption = QLabel("Prompt — แต่ละไฟล์เลือกวางเป็นไฟล์หรือข้อความ (เรียงชื่อ)")
        prompt_list_caption.setObjectName("info")
        self._row_prompt_caption = prompt_list_caption
        content_layout.addWidget(prompt_list_caption)

        self.prompt_list_scroll = QScrollArea()
        self.prompt_list_scroll.setObjectName("promptListScroll")
        self.prompt_list_scroll.setWidgetResizable(True)
        self.prompt_list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Height is sized dynamically in _resize_prompt_scroll_area():
        # ≤ PROMPT_ROWS_BEFORE_SCROLL → fits exactly, beyond → scroll.
        self.prompt_files_inner = QWidget()
        self.prompt_files_inner.setObjectName("promptFilesInner")
        self.prompt_rows_layout = QVBoxLayout()
        self.prompt_rows_layout.setContentsMargins(6, 6, 6, 6)
        self.prompt_rows_layout.setSpacing(6)
        self.prompt_files_inner.setLayout(self.prompt_rows_layout)
        self.prompt_list_scroll.setWidget(self.prompt_files_inner)
        self.prompt_list_scroll.setFrameShape(QFrame.Shape.NoFrame)
        vp = self.prompt_list_scroll.viewport()
        vp.setObjectName("promptListViewport")
        vp.setAutoFillBackground(False)
        self.prompt_files_inner.setAutoFillBackground(False)
        content_layout.addWidget(self.prompt_list_scroll)

        # -- chapter folder selector
        chapter_row = QHBoxLayout()
        self.chapter_btn = QPushButton("📁 Chapter Folder")
        self.chapter_btn.setObjectName("actionBtn")
        self.chapter_btn.clicked.connect(self._select_chapters)
        self.chapter_files_btn = QPushButton("📄 Files…")
        self.chapter_files_btn.setObjectName("controlBtn")
        self.chapter_files_btn.setToolTip("เลือกหลายไฟล์ chapter โดยตรง (แทนที่ของเดิม)")
        self.chapter_files_btn.clicked.connect(self._select_chapter_files_picker)
        self.chapter_add_files_btn = QPushButton("➕ เพิ่ม")
        self.chapter_add_files_btn.setObjectName("addBtn")
        self.chapter_add_files_btn.setToolTip("เพิ่มไฟล์ chapter ทีหลัง (ไม่ลบของเดิม)")
        self.chapter_add_files_btn.clicked.connect(self._add_chapter_files_picker)
        self.chapter_info = QLabel("--")
        self.chapter_info.setObjectName("info")
        self.chapter_info.setTextFormat(Qt.TextFormat.RichText)
        chapter_row.addWidget(self.chapter_btn)
        chapter_row.addWidget(self.chapter_files_btn)
        chapter_row.addWidget(self.chapter_add_files_btn)
        chapter_row.addWidget(self.chapter_info, 1)
        self._row_chapter = QWidget()
        self._row_chapter.setLayout(chapter_row)
        content_layout.addWidget(self._row_chapter)

        # -- chapter range filter + jump-to-chapter
        range_row = QHBoxLayout()
        range_label = QLabel("ตอนที่:")
        range_label.setObjectName("info")
        self.range_from = QLineEdit()
        self.range_from.setObjectName("numberInput")
        self.range_from.setPlaceholderText("From")
        self.range_from.setFixedWidth(70)
        self.range_from.setValidator(QIntValidator(0, 999999, self))
        self.range_from.returnPressed.connect(self._on_range_apply)
        self.range_to = QLineEdit()
        self.range_to.setObjectName("numberInput")
        self.range_to.setPlaceholderText("To")
        self.range_to.setFixedWidth(70)
        self.range_to.setValidator(QIntValidator(0, 999999, self))
        self.range_to.returnPressed.connect(self._on_range_apply)
        self.range_apply_btn = QPushButton("✓ Apply")
        self.range_apply_btn.setObjectName("controlBtn")
        self.range_apply_btn.clicked.connect(self._on_range_apply)
        self.range_reset_btn = QPushButton("↺ Reset")
        self.range_reset_btn.setObjectName("controlBtn")
        self.range_reset_btn.clicked.connect(self._on_range_reset)
        range_row.addWidget(range_label)
        range_row.addWidget(self.range_from)
        range_row.addWidget(QLabel("–"))
        range_row.addWidget(self.range_to)
        range_row.addWidget(self.range_apply_btn)
        range_row.addWidget(self.range_reset_btn)
        jump_label = QLabel("ไปตอนที่:")
        jump_label.setObjectName("info")
        self.jump_input = QLineEdit()
        self.jump_input.setObjectName("numberInput")
        self.jump_input.setPlaceholderText("เช่น 411")
        self.jump_input.setFixedWidth(80)
        self.jump_input.setValidator(QIntValidator(0, 999999, self))
        self.jump_input.returnPressed.connect(self._on_jump_submit)
        range_row.addWidget(jump_label)
        range_row.addWidget(self.jump_input)
        range_row.addStretch()
        self._row_range_jump = QWidget()
        self._row_range_jump.setLayout(range_row)
        content_layout.addWidget(self._row_range_jump)

        chapter_paste_row = QHBoxLayout()
        chapter_paste_label = QLabel("นิยาย (Chapter) วางเป็น:")
        chapter_paste_label.setObjectName("info")
        self.chapter_paste_file_radio = QRadioButton("ไฟล์")
        self.chapter_paste_file_radio.setObjectName("checkBox")
        self.chapter_paste_text_radio = QRadioButton("ข้อความ")
        self.chapter_paste_text_radio.setObjectName("checkBox")
        self.chapter_paste_group = QButtonGroup(self)
        self.chapter_paste_group.addButton(self.chapter_paste_file_radio, 0)
        self.chapter_paste_group.addButton(self.chapter_paste_text_radio, 1)
        self.chapter_paste_file_radio.setChecked(True)
        self.chapter_paste_group.buttonClicked.connect(self._on_chapter_paste_group)
        chapter_paste_row.addWidget(chapter_paste_label)
        chapter_paste_row.addWidget(self.chapter_paste_file_radio)
        chapter_paste_row.addWidget(self.chapter_paste_text_radio)
        chapter_paste_row.addStretch()
        self._row_chapter_paste = QWidget()
        self._row_chapter_paste.setLayout(chapter_paste_row)
        content_layout.addWidget(self._row_chapter_paste)

        # -- output folder selector (for Copy / Vocab modes)
        output_row = QHBoxLayout()
        self.output_btn = QPushButton("📁 Output Folder")
        self.output_btn.setObjectName("actionBtn")
        self.output_btn.clicked.connect(self._select_output)
        self.output_info = QLabel("--")
        self.output_info.setObjectName("info")
        output_row.addWidget(self.output_btn)
        output_row.addWidget(self.output_info, 1)
        self._row_output = QWidget()
        self._row_output.setLayout(output_row)
        content_layout.addWidget(self._row_output)

        # -- vocab filename input (Vocab mode only)
        vocab_row = QHBoxLayout()
        vocab_label = QLabel("Vocab file:")
        vocab_label.setObjectName("info")
        self.vocab_filename_input = QLineEdit(self.vocab_filename)
        self.vocab_filename_input.setObjectName("numberInput")
        self.vocab_filename_input.setPlaceholderText("vocab.txt")
        self.vocab_filename_input.setFixedWidth(200)
        self.vocab_filename_input.editingFinished.connect(self._on_vocab_filename_changed)
        vocab_row.addWidget(vocab_label)
        vocab_row.addWidget(self.vocab_filename_input)
        vocab_row.addStretch()
        self._row_vocab = QWidget()
        self._row_vocab.setLayout(vocab_row)
        content_layout.addWidget(self._row_vocab)

        # -- concurrent chapters selector (for Paste mode)
        concurrent_row = QHBoxLayout()
        concurrent_label = QLabel("Chapters per paste:")
        concurrent_label.setObjectName("info")
        self.concurrent_minus_btn = QPushButton("−")
        self.concurrent_minus_btn.setObjectName("controlBtn")
        self.concurrent_minus_btn.setFixedWidth(32)
        self.concurrent_minus_btn.clicked.connect(self._decrease_concurrent)
        self.concurrent_value_label = QLabel("1")
        self.concurrent_value_label.setObjectName("info")
        self.concurrent_value_label.setStyleSheet("font-weight: bold; min-width: 20px;")
        self.concurrent_plus_btn = QPushButton("+")
        self.concurrent_plus_btn.setObjectName("controlBtn")
        self.concurrent_plus_btn.setFixedWidth(32)
        self.concurrent_plus_btn.clicked.connect(self._increase_concurrent)
        concurrent_row.addWidget(concurrent_label)
        concurrent_row.addWidget(self.concurrent_minus_btn)
        concurrent_row.addWidget(self.concurrent_value_label)
        concurrent_row.addWidget(self.concurrent_plus_btn)
        concurrent_row.addStretch()
        self._row_concurrent = QWidget()
        self._row_concurrent.setLayout(concurrent_row)
        content_layout.addWidget(self._row_concurrent)

        # -- content start line selector (for Copy mode)
        line_row = QHBoxLayout()
        self.line_label = QLabel("Content at line:")
        self.line_label.setObjectName("info")
        self.line_minus_btn = QPushButton("−")
        self.line_minus_btn.setObjectName("controlBtn")
        self.line_minus_btn.setFixedWidth(32)
        self.line_minus_btn.clicked.connect(self._decrease_line)
        self.line_value_label = QLabel("3")
        self.line_value_label.setObjectName("info")
        self.line_value_label.setStyleSheet("font-weight: bold; min-width: 20px;")
        self.line_plus_btn = QPushButton("+")
        self.line_plus_btn.setObjectName("controlBtn")
        self.line_plus_btn.setFixedWidth(32)
        self.line_plus_btn.clicked.connect(self._increase_line)
        line_row.addWidget(self.line_label)
        line_row.addWidget(self.line_minus_btn)
        line_row.addWidget(self.line_value_label)
        line_row.addWidget(self.line_plus_btn)
        line_row.addStretch()
        self._row_line = QWidget()
        self._row_line.setLayout(line_row)
        content_layout.addWidget(self._row_line)

        copy_checkbox_row = QHBoxLayout()
        self.copy_template_checkbox = QCheckBox("Copy Mode: include filename + spacing")
        self.copy_template_checkbox.setObjectName("checkBox")
        self.copy_template_checkbox.setChecked(True)
        self.copy_template_checkbox.stateChanged.connect(self._on_copy_template_checkbox_changed)
        copy_checkbox_row.addWidget(self.copy_template_checkbox)
        copy_checkbox_row.addStretch()
        self._row_copy_template = QWidget()
        self._row_copy_template.setLayout(copy_checkbox_row)
        content_layout.addWidget(self._row_copy_template)

        # -- checkbox controls for prompt and chapter inclusion
        checkbox_row = QHBoxLayout()
        self.prompt_checkbox = QCheckBox("Include Prompt")
        self.prompt_checkbox.setObjectName("checkBox")
        self.prompt_checkbox.setChecked(True)
        self.prompt_checkbox.stateChanged.connect(self._on_prompt_checkbox_changed)
        
        self.chapter_checkbox = QCheckBox("Include Chapter")
        self.chapter_checkbox.setObjectName("checkBox")
        self.chapter_checkbox.setChecked(True)
        self.chapter_checkbox.stateChanged.connect(self._on_chapter_checkbox_changed)
        
        checkbox_row.addWidget(self.prompt_checkbox)
        checkbox_row.addWidget(self.chapter_checkbox)
        checkbox_row.addStretch()
        self._row_include_checkbox = QWidget()
        self._row_include_checkbox.setLayout(checkbox_row)
        content_layout.addWidget(self._row_include_checkbox)

        # -- fetch (refresh file lists after moving/adding files)
        self.fetch_btn = QPushButton("🔄 Fetch — อัปเดตรายการไฟล์")
        self.fetch_btn.setObjectName("actionBtn")
        self.fetch_btn.clicked.connect(self._fetch_folders)
        content_layout.addWidget(self.fetch_btn)

        # -- hotkey legend
        legend = QLabel(
            "Hotkeys:  F9 = Prev  |  F10 = Next  |  F12 = Pause/Resume\n"
            "Paste Mode: Ctrl+V triggers advance  |  Copy Mode: clipboard change triggers save"
        )
        legend.setObjectName("legend")
        legend.setWordWrap(True)
        content_layout.addWidget(legend)

        # -- control buttons row
        controls_row = QHBoxLayout()
        self.prev_btn = QPushButton("◀ Prev")
        self.prev_btn.setObjectName("controlBtn")
        self.prev_btn.clicked.connect(self._go_prev)

        self.pause_btn = QPushButton("⏸ Pause")
        self.pause_btn.setObjectName("controlBtn")
        self.pause_btn.clicked.connect(self._toggle_pause)

        self.next_btn = QPushButton("Next ▶")
        self.next_btn.setObjectName("controlBtn")
        self.next_btn.clicked.connect(self._go_next)

        self.reset_btn = QPushButton("↺ Reset")
        self.reset_btn.setObjectName("controlBtn")
        self.reset_btn.clicked.connect(self._reset_index)

        controls_row.addWidget(self.prev_btn)
        controls_row.addWidget(self.pause_btn)
        controls_row.addWidget(self.next_btn)
        controls_row.addWidget(self.reset_btn)
        content_layout.addLayout(controls_row)

        self.content_widget.setLayout(content_layout)
        root.addWidget(self.content_widget)

        self.setLayout(root)
        self.setMinimumWidth(520)

    # ============================================================ STYLING
    def _apply_styles(self):
        self.setStyleSheet("""
            QWidget {
                font-family: 'Segoe UI', 'Noto Sans Thai', sans-serif;
                font-size: 13px;
                color: #e0e0e0;
            }
            #title {
                font-size: 16px;
                font-weight: bold;
                color: #ffffff;
            }
            #status {
                font-size: 14px;
                padding: 6px 10px;
                background: rgba(255,255,255,0.07);
                border-radius: 8px;
                color: #90ee90;
            }
            #modeBtn {
                background: rgba(80,180,255,0.18);
                border: 1px solid rgba(80,180,255,0.35);
                border-radius: 8px;
                padding: 8px 14px;
                color: #80d4ff;
                font-size: 13px;
                font-weight: bold;
            }
            #modeBtn:hover {
                background: rgba(80,180,255,0.30);
            }
            #actionBtn {
                background: rgba(255,255,255,0.12);
                border: 1px solid rgba(255,255,255,0.18);
                border-radius: 8px;
                padding: 6px 14px;
                color: #ffffff;
            }
            #actionBtn:hover {
                background: rgba(255,255,255,0.22);
            }
            #controlBtn {
                background: rgba(255,255,255,0.10);
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 6px;
                padding: 6px 12px;
                color: #e0e0e0;
                font-size: 12px;
            }
            #controlBtn:hover {
                background: rgba(255,255,255,0.20);
            }
            #info {
                color: #aaaaaa;
                font-size: 12px;
            }
            #legend {
                font-size: 11px;
                color: #888888;
                margin-top: 4px;
            }
            QScrollArea#promptListScroll,
            QWidget#promptListViewport,
            QWidget#promptFilesInner {
                background: transparent;
                border: none;
            }
            #closeBtn {
                background: transparent;
                border: none;
                color: #888888;
                font-size: 16px;
            }
            #closeBtn:hover {
                color: #ff5555;
            }
            #minimizeBtn {
                background: transparent;
                border: none;
                color: #888888;
                font-size: 18px;
                font-weight: bold;
            }
            #minimizeBtn:hover {
                color: #ffffff;
            }
            #updateBtn {
                background: #2d5a2d;
                color: #aaffaa;
                border: 1px solid #3d7a3d;
                border-radius: 8px;
                padding: 1px 8px;
                margin-left: 8px;
                font-size: 11px;
                font-weight: bold;
            }
            #updateBtn:hover {
                background: #3d7a3d;
                color: #ffffff;
            }
            QCheckBox {
                spacing: 8px;
                color: #e0e0e0;
                padding: 2px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #6a7a8a;
                border-radius: 3px;
                background: rgba(255,255,255,0.05);
            }
            QCheckBox::indicator:hover {
                border-color: #4a9eff;
                background: rgba(74,158,255,0.10);
            }
            QCheckBox::indicator:checked {
                background: #2680eb;
                border: 1px solid #4a9eff;
                image: none;
            }
            QCheckBox::indicator:checked:hover {
                background: #3a8df0;
            }
            QRadioButton {
                spacing: 8px;
                color: #e0e0e0;
                padding: 2px;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #6a7a8a;
                border-radius: 8px;
                background: rgba(255,255,255,0.05);
            }
            QRadioButton::indicator:hover {
                border-color: #4a9eff;
                background: rgba(74,158,255,0.10);
            }
            QRadioButton::indicator:checked {
                background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
                    stop:0 #ffffff, stop:0.40 #ffffff, stop:0.45 #2680eb, stop:1 #2680eb);
                border: 1px solid #4a9eff;
            }
            QRadioButton::indicator:checked:hover {
                border-color: #6ab2ff;
            }
            #numberInput {
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.20);
                border-radius: 6px;
                padding: 4px 8px;
                color: #ffffff;
                font-size: 12px;
                selection-background-color: #2680eb;
            }
            #numberInput:focus {
                border: 1px solid #4a9eff;
                background: rgba(74,158,255,0.10);
            }
            #addBtn {
                background: rgba(80,200,120,0.18);
                border: 1px solid rgba(80,200,120,0.45);
                border-radius: 6px;
                padding: 6px 12px;
                color: #8eecb0;
                font-size: 12px;
                font-weight: bold;
            }
            #addBtn:hover {
                background: rgba(80,200,120,0.32);
                color: #ffffff;
            }
            #rowRemoveBtn {
                background: rgba(255,80,80,0.10);
                border: 1px solid rgba(255,80,80,0.30);
                border-radius: 4px;
                color: #ff8a8a;
                font-size: 11px;
                font-weight: bold;
                padding: 0;
            }
            #rowRemoveBtn:hover {
                background: rgba(255,80,80,0.30);
                color: #ffffff;
                border-color: #ff5555;
            }
        """)

    # override paintEvent so we get the rounded dark translucent background
    def paintEvent(self, event):
        from PyQt6.QtGui import QPainter, QBrush, QPainterPath
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 14, 14)
        painter.fillPath(path, QBrush(QColor(30, 30, 30, 204)))
        painter.end()

    # ============================================================ DRAGGING
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def event(self, e):
        if e.type() == self._get_paste_hotkey_event_type():
            self._paste_hotkey_timer.stop()
            delay = (
                self.staged_ms_after_user_paste
                if self._staged_pending_file_paths is not None
                else self.staged_ms_simple_paste
            )
            delay = max(50, min(delay, 8000))
            self._paste_hotkey_timer.start(delay)
            return True
        return super().event(e)

    # ============================================================ CONFIG
    def _load_saved_config(self):
        cfg = load_config()
        if cfg.get("prompt_folder"):
            pf = cfg["prompt_folder"]
            if pf.lower().endswith(".lnk"):
                resolved = _resolve_shortcut(pf)
                if resolved and os.path.isdir(resolved):
                    self.prompt_folder = resolved
                    self._scan_prompt_folder()
                elif os.path.isfile(pf):
                    self.prompt_folder = pf
                    self._scan_prompt_folder()
            elif os.path.isdir(pf):
                self.prompt_folder = pf
                self._scan_prompt_folder()
        if cfg.get("chapter_folder"):
            cf = cfg["chapter_folder"]
            if cf.lower().endswith(".lnk"):
                resolved = _resolve_shortcut(cf)
                if resolved and os.path.isdir(resolved):
                    self.chapter_folder = resolved
                    self._scan_chapter_folder()
                elif os.path.isfile(cf):
                    self.chapter_folder = cf
                    self._scan_chapter_folder()
            elif os.path.isdir(cf):
                self.chapter_folder = cf
                self._scan_chapter_folder()
        if cfg.get("output_folder") and os.path.isdir(cfg["output_folder"]):
            self.output_folder = cfg["output_folder"]
            self.output_info.setText(Path(self.output_folder).name)
        self.content_start_line = cfg.get("content_start_line", 3)
        self.line_value_label.setText(str(self.content_start_line))
        self.concurrent_chapters = cfg.get("concurrent_chapters", 1)
        self.concurrent_value_label.setText(str(self.concurrent_chapters))
        self.include_prompt = cfg.get("include_prompt", True)
        self.prompt_checkbox.setChecked(self.include_prompt)
        self.include_chapter = cfg.get("include_chapter", True)
        self.chapter_checkbox.setChecked(self.include_chapter)
        self.copy_template_enabled = cfg.get("copy_template_enabled", True)
        self.copy_template_checkbox.setChecked(self.copy_template_enabled)
        self._update_copy_template_controls()
        if "prompt_paste_modes" in cfg and isinstance(cfg["prompt_paste_modes"], dict):
            self.prompt_paste_modes = {str(k): bool(v) for k, v in cfg["prompt_paste_modes"].items()}
            self._legacy_prompt_all_text = None
        else:
            self.prompt_paste_modes = {}
            self._legacy_prompt_all_text = bool(cfg.get("prompt_paste_as_text", False))
        self.chapter_paste_as_text = cfg.get("chapter_paste_as_text", False)
        self.chapter_paste_text_radio.setChecked(self.chapter_paste_as_text)
        self.chapter_paste_file_radio.setChecked(not self.chapter_paste_as_text)
        self.vocab_filename = (cfg.get("vocab_filename") or "vocab.txt").strip() or "vocab.txt"
        if hasattr(self, "vocab_filename_input"):
            self.vocab_filename_input.setText(self.vocab_filename)
        self.staged_ms_after_user_paste = max(50, min(int(cfg.get("staged_ms_after_user_paste", 300)), 8000))
        self.staged_ms_clipboard_to_ctrl_v = max(30, min(int(cfg.get("staged_ms_clipboard_to_ctrl_v", 60)), 3000))
        self.staged_ms_after_text_paste = max(50, min(int(cfg.get("staged_ms_after_text_paste", 150)), 8000))
        self.staged_ms_simple_paste = max(40, min(int(cfg.get("staged_ms_simple_paste", 90)), 3000))
        self._try_init()

    def _save_config(self):
        save_config({
            "prompt_folder": self.prompt_folder or "",
            "chapter_folder": self.chapter_folder or "",
            "output_folder": self.output_folder or "",
            "content_start_line": self.content_start_line,
            "concurrent_chapters": self.concurrent_chapters,
            "include_prompt": self.include_prompt,
            "include_chapter": self.include_chapter,
            "copy_template_enabled": self.copy_template_enabled,
            "prompt_paste_modes": self.prompt_paste_modes,
            "chapter_paste_as_text": self.chapter_paste_as_text,
            "vocab_filename": self.vocab_filename,
            "staged_ms_after_user_paste": self.staged_ms_after_user_paste,
            "staged_ms_clipboard_to_ctrl_v": self.staged_ms_clipboard_to_ctrl_v,
            "staged_ms_after_text_paste": self.staged_ms_after_text_paste,
            "staged_ms_simple_paste": self.staged_ms_simple_paste,
        })

    # ============================================================ FILE SELECTORS
    def _select_prompt(self):
        start = self.prompt_folder or ""
        folder = QFileDialog.getExistingDirectory(self, "Select Prompt Folder", start)
        if folder:
            self.prompt_folder = folder
            self._scan_prompt_folder()
            self._save_config()
            self._try_init()

    def _scan_prompt_folder(self):
        base = self.prompt_folder
        if not base:
            self.prompt_files = []
            self.prompt_info.setText("--")
            self._rebuild_prompt_file_rows()
            return
        if base.lower().endswith(".lnk"):
            resolved = _resolve_shortcut(base)
            if resolved and os.path.isdir(resolved):
                base = resolved
        if not os.path.isdir(base):
            self.prompt_files = []
            self.prompt_info.setText("--")
            self._rebuild_prompt_file_rows()
            return
        files = [
            f
            for f in os.listdir(base)
            if os.path.isfile(os.path.join(base, f))
            and (
                f.lower().endswith(".txt")
                or f.lower().endswith(".md")
                or f.lower().endswith(".lnk")
            )
        ]
        entries: list[tuple[str, str]] = []
        for f in natsort.natsorted(files):
            path = _resolve_path_maybe_shortcut(base, f)
            if f.lower().endswith(".lnk"):
                if path and os.path.isfile(path):
                    entries.append((f, path))
            else:
                entries.append((f, path))
        # เรียงชื่อไฟล์ตามตัวอักษร (ไม่สนตัวพิมพ์) ให้ตรงกับรายการที่แสดง
        self.prompt_files = sorted(entries, key=lambda t: t[0].lower())
        n = len(self.prompt_files)
        self.prompt_info.setText(
            f"<b>{n}</b> ไฟล์ · [{Path(base).name}]" if n else "ไม่มีไฟล์ .md/.txt/.lnk"
        )
        self._rebuild_prompt_file_rows()

    def _select_chapters(self):
        start = self.chapter_folder or ""
        folder = QFileDialog.getExistingDirectory(self, "Select Chapter Folder", start)
        if folder:
            self.chapter_folder = folder
            self._chapter_range = None
            if hasattr(self, "range_from"):
                self.range_from.clear()
                self.range_to.clear()
            self._scan_chapter_folder()
            self.current_index = 0
            self._save_config()
            self._try_init()

    def _scan_chapter_folder(self):
        base = self.chapter_folder
        if not base:
            self._chapter_files_all = []
            self.chapter_files = []
            self._chapter_idx_by_num = {}
            self.chapter_info.setText("--")
            return
        if base.lower().endswith(".lnk"):
            resolved = _resolve_shortcut(base)
            if resolved and os.path.isdir(resolved):
                base = resolved
        if not os.path.isdir(base):
            self._chapter_files_all = []
            self.chapter_files = []
            self._chapter_idx_by_num = {}
            self.chapter_info.setText("--")
            return
        files = [
            f
            for f in os.listdir(base)
            if os.path.isfile(os.path.join(base, f))
            and (
                f.lower().endswith(".txt")
                or f.lower().endswith(".md")
                or f.lower().endswith(".lnk")
            )
        ]
        entries: list[tuple[str, str]] = []
        for f in natsort.natsorted(files):
            path = _resolve_path_maybe_shortcut(base, f)
            if f.lower().endswith(".lnk"):
                if path and os.path.isfile(path):
                    entries.append((f, path))
            else:
                entries.append((f, path))
        self._chapter_files_all = entries
        self._apply_chapter_range_filter(reset_current_index=False)

    # ---------------- chapter number / range helpers ----------------
    def _rebuild_chapter_index_map(self):
        self._chapter_idx_by_num = {}
        for i, (name, _) in enumerate(self.chapter_files):
            n = _detect_chapter_number(name)
            if n is not None:
                self._chapter_idx_by_num.setdefault(n, i)

    def _apply_chapter_range_filter(self, *, reset_current_index: bool):
        """Rebuild self.chapter_files from self._chapter_files_all using self._chapter_range."""
        if self._chapter_range is None:
            self.chapter_files = list(self._chapter_files_all)
        else:
            lo, hi = self._chapter_range
            filtered: list[tuple[str, str]] = []
            for name, path in self._chapter_files_all:
                n = _detect_chapter_number(name)
                if n is None:
                    continue
                if lo is not None and n < lo:
                    continue
                if hi is not None and n > hi:
                    continue
                filtered.append((name, path))
            self.chapter_files = filtered
        if reset_current_index:
            self.current_index = 0
        elif self.chapter_files and self.current_index >= len(self.chapter_files):
            self.current_index = max(0, len(self.chapter_files) - 1)
        self._rebuild_chapter_index_map()

        n = len(self.chapter_files)
        base_name = Path(self.chapter_folder).name if self.chapter_folder else ""
        suffix = ""
        if self._chapter_range is not None:
            lo, hi = self._chapter_range
            # Treat 0 / negative as no bound so we never display 'ตอน 0000'.
            lo_disp = lo if (lo is not None and lo > 0) else None
            hi_disp = hi if (hi is not None and hi > 0) else None
            if lo_disp is not None or hi_disp is not None:
                lo_s = f"{lo_disp:04d}" if lo_disp is not None else "..."
                hi_s = f"{hi_disp:04d}" if hi_disp is not None else "..."
                suffix = f" · ตอน {lo_s}–{hi_s}"
        if n:
            self.chapter_info.setText(f"<b>{n}</b> ไฟล์ · [{base_name}]{suffix}")
        else:
            self.chapter_info.setText("ไม่มีไฟล์ .md/.txt/.lnk" if not self._chapter_files_all else f"ไม่มีไฟล์ใน{suffix}")

    def _ch_num_at(self, idx: int) -> int | None:
        if 0 <= idx < len(self.chapter_files):
            return _detect_chapter_number(self.chapter_files[idx][0])
        return None

    def _ch_label(self, idx: int) -> str:
        n = self._ch_num_at(idx)
        if n is not None:
            return f"ตอน {n:04d}"
        if 0 <= idx < len(self.chapter_files):
            return self.chapter_files[idx][0]
        return ""

    def _ch_range_label(self, start_idx: int, end_idx: int) -> str:
        a = self._ch_num_at(start_idx)
        b = self._ch_num_at(end_idx)
        if a is not None and b is not None:
            if a == b:
                return f"ตอน {a:04d}"
            return f"ตอน {a:04d}–{b:04d}"
        return f"#{start_idx+1}-#{end_idx+1}"

    def _on_jump_submit(self):
        text = self.jump_input.text().strip()
        if not text:
            return
        try:
            n = int(text)
        except ValueError:
            self.jump_input.clear()
            return
        target_idx = self._chapter_idx_by_num.get(n)
        if target_idx is None:
            for i, (name, _) in enumerate(self.chapter_files):
                num = _detect_chapter_number(name)
                if num is not None and num >= n:
                    target_idx = i
                    break
        if target_idx is not None:
            # Snap to the START of the group containing the target so groups stay
            # aligned to the file-list rhythm — e.g. start=601, concurrent=3:
            # jump 602 → 601–603, jump 606 → 604–606, jump 611 → 610–612.
            group = max(1, self.concurrent_chapters)
            self.current_index = (target_idx // group) * group
            self._update_status()
        self.jump_input.clear()

    def _on_range_apply(self):
        lo_text = self.range_from.text().strip()
        hi_text = self.range_to.text().strip()
        try:
            lo = int(lo_text) if lo_text else None
            hi = int(hi_text) if hi_text else None
        except ValueError:
            return
        if lo is not None and lo <= 0:
            lo = None
        if hi is not None and hi <= 0:
            hi = None
        if lo is None and hi is None:
            self._chapter_range = None
        else:
            if lo is not None and hi is not None and lo > hi:
                lo, hi = hi, lo
            self._chapter_range = (lo, hi)
        self._apply_chapter_range_filter(reset_current_index=True)
        self._update_status()

    def _on_range_reset(self):
        self.range_from.clear()
        self.range_to.clear()
        self._chapter_range = None
        self._apply_chapter_range_filter(reset_current_index=True)
        self._update_status()

    # ---------------- file pickers (Open Files / Append) ----------------
    def _select_chapter_files_picker(self):
        self._chapter_files_picker(append=False)

    def _add_chapter_files_picker(self):
        self._chapter_files_picker(append=True)

    def _chapter_files_picker(self, *, append: bool):
        start = self.chapter_folder or ""
        title = "Add Chapter Files" if append else "Select Chapter Files"
        files, _ = QFileDialog.getOpenFileNames(
            self, title, start, "Text Files (*.txt *.md *.lnk);;All Files (*)"
        )
        if not files:
            return
        new_entries: list[tuple[str, str]] = []
        for full in files:
            name = os.path.basename(full)
            path = _resolve_path_maybe_shortcut(os.path.dirname(full), name)
            if name.lower().endswith(".lnk"):
                if path and os.path.isfile(path):
                    new_entries.append((name, path))
            else:
                new_entries.append((name, path))
        if append and self._chapter_files_all:
            existing_paths = {p for _, p in self._chapter_files_all}
            merged = list(self._chapter_files_all)
            for name, path in new_entries:
                if path not in existing_paths:
                    merged.append((name, path))
                    existing_paths.add(path)
            merged = natsort.natsorted(merged, key=lambda t: t[0])
            self._chapter_files_all = merged
        else:
            sorted_new = natsort.natsorted(new_entries, key=lambda t: t[0])
            self._chapter_files_all = sorted_new
            try:
                common = os.path.commonpath([p for p in files])
            except ValueError:
                common = os.path.dirname(files[0])
            if not os.path.isdir(common):
                common = os.path.dirname(files[0])
            self.chapter_folder = common
            self._chapter_range = None
            self.range_from.clear()
            self.range_to.clear()
        self._apply_chapter_range_filter(reset_current_index=not append)
        self._save_config()
        self._try_init()

    def _select_prompt_files_picker(self):
        self._prompt_files_picker(append=False)

    def _add_prompt_files_picker(self):
        self._prompt_files_picker(append=True)

    def _prompt_files_picker(self, *, append: bool):
        start = self.prompt_folder or ""
        title = "Add Prompt Files" if append else "Select Prompt Files"
        files, _ = QFileDialog.getOpenFileNames(
            self, title, start, "Text Files (*.txt *.md *.lnk);;All Files (*)"
        )
        if not files:
            return
        new_entries: list[tuple[str, str]] = []
        for full in files:
            name = os.path.basename(full)
            path = _resolve_path_maybe_shortcut(os.path.dirname(full), name)
            if name.lower().endswith(".lnk"):
                if path and os.path.isfile(path):
                    new_entries.append((name, path))
            else:
                new_entries.append((name, path))
        if append and self.prompt_files:
            existing_paths = {p for _, p in self.prompt_files}
            merged = list(self.prompt_files)
            for name, path in new_entries:
                if path not in existing_paths:
                    merged.append((name, path))
                    existing_paths.add(path)
            self.prompt_files = sorted(merged, key=lambda t: t[0].lower())
        else:
            self.prompt_files = sorted(new_entries, key=lambda t: t[0].lower())
            try:
                common = os.path.commonpath([p for p in files])
            except ValueError:
                common = os.path.dirname(files[0])
            if not os.path.isdir(common):
                common = os.path.dirname(files[0])
            self.prompt_folder = common
        n = len(self.prompt_files)
        self.prompt_info.setText(f"<b>{n}</b> ไฟล์ · [picked]" if n else "--")
        self._rebuild_prompt_file_rows()
        self._save_config()
        self._try_init()

    def _remove_prompt_file(self, display_name: str):
        before = len(self.prompt_files)
        self.prompt_files = [(n, p) for (n, p) in self.prompt_files if n != display_name]
        if len(self.prompt_files) == before:
            return
        self.prompt_paste_modes.pop(display_name, None)
        n = len(self.prompt_files)
        base = Path(self.prompt_folder).name if self.prompt_folder else ""
        self.prompt_info.setText(f"<b>{n}</b> ไฟล์ · [{base}]" if n else "--")
        self._rebuild_prompt_file_rows()
        self._save_config()
        if self.mode == self.MODE_PASTE:
            self._load_clipboard_paste_mode()

    def _on_vocab_filename_changed(self):
        text = (self.vocab_filename_input.text() or "").strip()
        if not text:
            text = "vocab.txt"
        if not os.path.splitext(text)[1]:
            text += ".txt"
        if text == self.vocab_filename:
            return
        self.vocab_filename = text
        self.vocab_filename_input.setText(text)
        if self.mode == self.MODE_VOCAB:
            self.mode_btn.setText(f"📖 [VOCAB MODE]  Clipboard → {self.vocab_filename} (append)")
            self._init_vocab_mode()
        self._save_config()

    def _apply_mode_visibility(self):
        is_paste = self.mode == self.MODE_PASTE
        is_copy = self.mode == self.MODE_COPY
        is_vocab = self.mode == self.MODE_VOCAB

        self._row_prompt.setVisible(is_paste)
        self._row_prompt_caption.setVisible(is_paste)
        self.prompt_list_scroll.setVisible(is_paste)
        self._row_chapter_paste.setVisible(is_paste)
        self._row_include_checkbox.setVisible(is_paste)

        self._row_chapter.setVisible(is_paste or is_copy)
        self._row_range_jump.setVisible(is_paste or is_copy)
        self._row_concurrent.setVisible(is_paste or is_copy)

        self._row_output.setVisible(is_copy or is_vocab)

        self._row_line.setVisible(is_copy)
        self._row_copy_template.setVisible(is_copy)

        self._row_vocab.setVisible(is_vocab)

        self.adjustSize()

    def _increase_line(self):
        self.content_start_line += 1
        self.line_value_label.setText(str(self.content_start_line))
        self._save_config()

    def _decrease_line(self):
        if self.content_start_line > 1:
            self.content_start_line -= 1
            self.line_value_label.setText(str(self.content_start_line))
            self._save_config()

    def _increase_concurrent(self):
        if self.chapter_files and self.concurrent_chapters < len(self.chapter_files):
            self.concurrent_chapters += 1
            self.concurrent_value_label.setText(str(self.concurrent_chapters))
            self._save_config()
            if self.mode == self.MODE_PASTE:
                self._load_clipboard_paste_mode()

    def _decrease_concurrent(self):
        if self.concurrent_chapters > 1:
            self.concurrent_chapters -= 1
            self.concurrent_value_label.setText(str(self.concurrent_chapters))
            self._save_config()
            if self.mode == self.MODE_PASTE:
                self._load_clipboard_paste_mode()

    def _on_prompt_checkbox_changed(self, state):
        """Handle prompt checkbox state change."""
        self.include_prompt = (state == Qt.CheckState.Checked.value)
        self._save_config()
        if self.mode == self.MODE_PASTE:
            self._load_clipboard_paste_mode()

    def _on_chapter_checkbox_changed(self, state):
        """Handle chapter checkbox state change."""
        self.include_chapter = (state == Qt.CheckState.Checked.value)
        self._save_config()
        if self.mode == self.MODE_PASTE:
            self._load_clipboard_paste_mode()

    def _on_chapter_paste_group(self, _button):
        self.chapter_paste_as_text = self.chapter_paste_text_radio.isChecked()
        self._save_config()
        if self.mode == self.MODE_PASTE:
            self._load_clipboard_paste_mode()

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _sync_prompt_paste_modes_with_file_list(self) -> bool:
        """Return True if config was migrated from legacy prompt_paste_as_text (caller may save)."""
        names = [t[0] for t in self.prompt_files]
        name_set = set(names)
        for k in list(self.prompt_paste_modes.keys()):
            if k not in name_set:
                del self.prompt_paste_modes[k]
        legacy = self._legacy_prompt_all_text
        if legacy is not None:
            for n in names:
                self.prompt_paste_modes[n] = legacy
            self._legacy_prompt_all_text = None
            return True
        for n in names:
            self.prompt_paste_modes.setdefault(n, False)
        return False

    def _rebuild_prompt_file_rows(self):
        if not hasattr(self, "prompt_rows_layout"):
            return
        self._clear_layout(self.prompt_rows_layout)
        if not self.prompt_files:
            return
        if self._sync_prompt_paste_modes_with_file_list():
            self._save_config()
        for display_name, _path in self.prompt_files:
            row = QWidget()
            row_h = QHBoxLayout(row)
            row_h.setContentsMargins(0, 0, 0, 0)
            row_h.setSpacing(8)
            nm = QLabel(display_name)
            nm.setObjectName("info")
            nm.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            nm.setWordWrap(True)
            nm.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            rb_file = QRadioButton("ไฟล์")
            rb_file.setObjectName("checkBox")
            rb_text = QRadioButton("ข้อความ")
            rb_text.setObjectName("checkBox")
            grp = QButtonGroup(row)
            grp.addButton(rb_file, 0)
            grp.addButton(rb_text, 1)
            if self.prompt_paste_modes.get(display_name, False):
                rb_text.setChecked(True)
            else:
                rb_file.setChecked(True)

            def _on_prompt_row_mode(_btn, dn=display_name, rt=rb_text):
                self.prompt_paste_modes[dn] = rt.isChecked()
                self._save_config()
                if self.mode == self.MODE_PASTE:
                    self._load_clipboard_paste_mode()

            grp.buttonClicked.connect(_on_prompt_row_mode)

            remove_btn = QPushButton("✕")
            remove_btn.setObjectName("rowRemoveBtn")
            remove_btn.setToolTip("ลบไฟล์นี้ออกจากรายการ (ไฟล์ต้นฉบับไม่ถูกลบ)")
            remove_btn.setFixedSize(22, 22)
            remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            remove_btn.clicked.connect(lambda _checked=False, dn=display_name: self._remove_prompt_file(dn))

            row_h.addWidget(nm, 1)
            row_h.addWidget(rb_file, 0)
            row_h.addWidget(rb_text, 0)
            row_h.addWidget(remove_btn, 0)
            self.prompt_rows_layout.addWidget(row)
        self.prompt_rows_layout.addStretch()
        self._resize_prompt_scroll_area()

    def _resize_prompt_scroll_area(self):
        """Size the prompt list to fit all rows up to PROMPT_ROWS_BEFORE_SCROLL,
        then scroll for any extras."""
        n = len(self.prompt_files)
        if n == 0:
            self.prompt_list_scroll.setFixedHeight(0)
            return
        self.prompt_files_inner.adjustSize()
        layout_margins = 12  # 6 top + 6 bottom from setContentsMargins
        row_spacing = 6      # from setSpacing
        rows_to_show = min(n, self.PROMPT_ROWS_BEFORE_SCROLL)
        # Measure the actual heights of the first rows_to_show rows.
        row_heights: list[int] = []
        for i in range(rows_to_show):
            item = self.prompt_rows_layout.itemAt(i)
            w = item.widget() if item else None
            if w is not None:
                row_heights.append(max(w.sizeHint().height(), 28))
        if not row_heights:
            self.prompt_list_scroll.setFixedHeight(0)
            return
        total = sum(row_heights) + row_spacing * (len(row_heights) - 1) + layout_margins
        self.prompt_list_scroll.setFixedHeight(total + 4)  # small fudge for borders

    @staticmethod
    def _read_local_file_as_text(path: str, label: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except OSError:
            return f"[อ่านไฟล์ไม่ได้: {label}]"

    def _on_copy_template_checkbox_changed(self, state):
        self.copy_template_enabled = (state == Qt.CheckState.Checked.value)
        self._update_copy_template_controls()
        self._save_config()

    def _update_copy_template_controls(self):
        self.line_label.setEnabled(self.copy_template_enabled)
        self.line_minus_btn.setEnabled(self.copy_template_enabled)
        self.line_value_label.setEnabled(self.copy_template_enabled)
        self.line_plus_btn.setEnabled(self.copy_template_enabled)

    def _fetch_folders(self):
        """Re-scan Prompt + Chapter folders so file list is up to date after moving/adding files."""
        if self.prompt_folder and os.path.isdir(self.prompt_folder):
            self._scan_prompt_folder()
        if self.chapter_folder and os.path.isdir(self.chapter_folder):
            self._scan_chapter_folder()
        # Clamp index if list got shorter
        if self.chapter_files and self.current_index >= len(self.chapter_files):
            self.current_index = max(0, len(self.chapter_files) - 1)
        self._try_init()
        self._update_status()

    def _select_output(self):
        start = self.output_folder or ""
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder", start)
        if folder:
            self.output_folder = folder
            self.output_info.setText(Path(folder).name)
            self._save_config()

    # ============================================================ MODE TOGGLE
    def _toggle_mode(self):
        if self.mode == self.MODE_PASTE:
            self.mode = self.MODE_COPY
            self.mode_btn.setText("📝 [COPY MODE]  Clipboard text → .txt files")
            self.mode_btn.setStyleSheet(
                "#modeBtn { background: rgba(255,160,50,0.20); border: 1px solid rgba(255,160,50,0.40); "
                "border-radius: 8px; padding: 8px 14px; color: #ffb347; font-size: 13px; font-weight: bold; }"
                "#modeBtn:hover { background: rgba(255,160,50,0.35); }"
            )
            self._start_clipboard_monitor()
        elif self.mode == self.MODE_COPY:
            self.mode = self.MODE_VOCAB
            self.mode_btn.setText(f"📖 [VOCAB MODE]  Clipboard → {self.vocab_filename} (append)")
            self.mode_btn.setStyleSheet(
                "#modeBtn { background: rgba(180,100,255,0.20); border: 1px solid rgba(180,100,255,0.40); "
                "border-radius: 8px; padding: 8px 14px; color: #c896ff; font-size: 13px; font-weight: bold; }"
                "#modeBtn:hover { background: rgba(180,100,255,0.35); }"
            )
            self._init_vocab_mode()
        else:
            self.mode = self.MODE_PASTE
            self.mode_btn.setText("📋 [PASTE MODE]  Prompt+Chapter → Clipboard")
            self.mode_btn.setStyleSheet("")
            self._stop_clipboard_monitor()
        self.paused = False
        self.pause_btn.setText("⏸ Pause")
        self._apply_mode_visibility()
        self._update_status()

    # ============================================================ INIT SYSTEM
    def _try_init(self):
        if self.mode == self.MODE_PASTE:
            if self.prompt_files and self.chapter_files:
                self._load_clipboard_paste_mode()
                self._register_hotkeys()
        else:
            self._register_hotkeys()
        self._update_status()

    def _init_vocab_mode(self):
        """Initialize vocab mode: create the configured vocab file in output folder if needed."""
        if not self.output_folder:
            self.status_label.setText("!! Set Output Folder first for vocab mode")
            return

        filename = (self.vocab_filename or "vocab.txt").strip() or "vocab.txt"
        if not os.path.splitext(filename)[1]:
            filename += ".txt"
        self.vocab_filename = filename
        self.vocab_file_path = os.path.join(self.output_folder, filename)
        
        # Count existing entries if file exists
        if os.path.isfile(self.vocab_file_path):
            with open(self.vocab_file_path, "r", encoding="utf-8") as f:
                content = f.read()
                # Count non-empty blocks separated by blank lines
                blocks = [b.strip() for b in content.split("\n\n") if b.strip()]
                self.vocab_entry_count = len(blocks)
        else:
            self.vocab_entry_count = 0
        
        self._start_clipboard_monitor()
        self._update_status()

    def _register_hotkeys(self):
        if self.hotkeys_registered:
            return
        self.hotkeys_registered = True

        keyboard.on_press_key("v", self._kb_paste_handler, suppress=False)
        keyboard.add_hotkey("f9", lambda: self.signals.prev_chapter.emit())
        keyboard.add_hotkey("f10", lambda: self.signals.next_chapter.emit())
        keyboard.add_hotkey("f12", lambda: self.signals.toggle_pause.emit())

    def _kb_paste_handler(self, event):
        if self._suppress_paste_hotkey:
            return
        if self.mode == self.MODE_PASTE and keyboard.is_pressed("ctrl") and not self.paused:
            # จาก thread ของ keyboard — ส่ง event เข้า Qt main thread (threading.Timer+emit เดิมทำให้ขั้นต่อไม่ทำงาน)
            QApplication.postEvent(self, QEvent(self._get_paste_hotkey_event_type()))

    # ============================================================ CLIPBOARD MONITOR (Copy Mode)
    def _start_clipboard_monitor(self):
        clipboard = QApplication.clipboard()
        self._last_clipboard_text = clipboard.text() or ""
        clipboard.dataChanged.connect(self._clipboard_data_changed)

    def _stop_clipboard_monitor(self):
        try:
            clipboard = QApplication.clipboard()
            clipboard.dataChanged.disconnect(self._clipboard_data_changed)
        except TypeError:
            pass
        # Cancel any pending deferred check
        if self._clipboard_check_timer is not None:
            self._clipboard_check_timer.stop()
            self._clipboard_check_timer = None

    def _clipboard_data_changed(self):
        """On Windows, clipboard may not be updated yet when dataChanged fires. Defer read."""
        if (self.mode != self.MODE_COPY and self.mode != self.MODE_VOCAB) or self.paused or self._ignore_clipboard_change:
            return
        # Cancel previous deferred check so we only have one pending
        if self._clipboard_check_timer is not None:
            self._clipboard_check_timer.stop()
        self._clipboard_check_timer = QTimer(self)
        self._clipboard_check_timer.setSingleShot(True)
        self._clipboard_check_timer.timeout.connect(self._clipboard_check_deferred)
        self._clipboard_check_timer.start(120)  # ms: give Windows time to finish updating clipboard

    def _clipboard_check_deferred(self):
        """Read clipboard after a short delay and trigger save if text changed."""
        self._clipboard_check_timer = None
        if (self.mode != self.MODE_COPY and self.mode != self.MODE_VOCAB) or self.paused or self._ignore_clipboard_change:
            return
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if text and text.strip() and text != self._last_clipboard_text:
            self._last_clipboard_text = text
            self.signals.clipboard_changed.emit()

    def _on_clipboard_changed(self):
        """Copy/Vocab mode: write clipboard text to files."""
        if self.mode == self.MODE_VOCAB:
            self._on_vocab_clipboard_changed()
        else:
            self._on_copy_clipboard_changed()

    def _on_copy_clipboard_changed(self):
        """Copy mode: write clipboard text into current chapter .txt template."""
        if not self.chapter_files or not self.output_folder:
            self.status_label.setText("!! Set Chapter Folder + Output Folder first")
            return
        if self.current_index >= len(self.chapter_files):
            self.status_label.setText("[DONE] All chapters saved")
            return

        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if not text:
            return

        total = len(self.chapter_files)
        chapters_remaining = total - self.current_index
        chapters_in_round = min(self.concurrent_chapters, chapters_remaining)
        first_ch_name = self.chapter_files[self.current_index][0]
        last_ch_name = self.chapter_files[self.current_index + chapters_in_round - 1][0]
        out_name, ch_title = copy_mode_group_output_name(first_ch_name, last_ch_name)

        if self.copy_template_enabled:
            blank_lines_needed = max(0, self.content_start_line - 1)
            content = f"{ch_title}" + "\n" * blank_lines_needed + f"{text}\n"
        else:
            content = f"{text}\n"

        out_path = os.path.join(self.output_folder, out_name)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)

        end_slot = self.current_index + chapters_in_round
        ch_label = self._ch_range_label(self.current_index, end_slot - 1)
        if chapters_in_round == 1:
            prog = f"{ch_label}  ({self.current_index + 1}/{total})"
        else:
            prog = f"{ch_label}  ({self.current_index + 1}-{end_slot}/{total})"
        self._show_toast(f"💾 SAVED: {prog}", "copy")

        self.status_label.setText(f"[SAVED] {prog}")
        self.status_label.setStyleSheet(
            "#status { color: #80ff80; background: rgba(255,255,255,0.07); "
            "border-radius: 8px; padding: 6px 10px; font-size: 14px; }"
        )

        self.current_index += chapters_in_round
        if self.current_index < len(self.chapter_files):
            QTimer.singleShot(1500, self._update_status)
        else:
            QTimer.singleShot(1500, lambda: self.status_label.setText("[DONE] All chapters saved"))

    def _on_vocab_clipboard_changed(self):
        """Vocab mode: append clipboard text to vocab.txt with blank line separator."""
        if not self.vocab_file_path:
            self.status_label.setText("!! Vocab mode not initialized")
            return

        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if not text or not text.strip():
            return

        # Append to vocab.txt
        with open(self.vocab_file_path, "a", encoding="utf-8") as f:
            if self.vocab_entry_count > 0:
                # Add blank line separator before new entry
                f.write("\n\n")
            f.write(text.strip())
        
        self.vocab_entry_count += 1
        
        self._show_toast(f"📝 VOCAB SAVED: Entry #{self.vocab_entry_count}", "vocab")
        
        self.status_label.setText(
            f"[SAVED] Vocab entry #{self.vocab_entry_count}"
        )
        self.status_label.setStyleSheet(
            "#status { color: #c896ff; background: rgba(255,255,255,0.07); "
            "border-radius: 8px; padding: 6px 10px; font-size: 14px; }"
        )
        
        QTimer.singleShot(1500, self._update_status)

    # ============================================================ PASTE MODE CLIPBOARD
    def _load_clipboard_paste_mode(self):
        if not self.chapter_files:
            return

        self._staged_pending_file_paths = None
        self._staged_plain_text_for_repeat = None
        self._staged_sequence_active = False
        self._ignore_clipboard_change = True

        clipboard = QApplication.clipboard()
        mime = QMimeData()

        # ลำดับในเนื้อหา: prompt ทั้งหมดก่อน แล้ว chapter ตาม concurrent
        # แต่ละชิ้นเป็น ("text", เนื้อหา) หรือ ("file", path สำหรับ URI)
        ordered_parts: list[tuple[str, str]] = []

        if self.include_prompt:
            for display_name, prompt_path in self.prompt_files:
                if self.prompt_paste_modes.get(display_name, False):
                    ordered_parts.append(
                        ("text", self._read_local_file_as_text(prompt_path, display_name))
                    )
                else:
                    ordered_parts.append(("file", prompt_path))

        if self.include_chapter:
            chapters_to_add = min(self.concurrent_chapters, len(self.chapter_files) - self.current_index)
            for i in range(chapters_to_add):
                chapter_idx = self.current_index + i
                ch_name, chapter_path = self.chapter_files[chapter_idx]
                if self.chapter_paste_as_text:
                    ordered_parts.append(
                        ("text", self._read_local_file_as_text(chapter_path, ch_name))
                    )
                else:
                    ordered_parts.append(("file", chapter_path))

        has_text = any(kind == "text" for kind, _ in ordered_parts)
        has_file = any(kind == "file" for kind, _ in ordered_parts)

        # แอปเว็บมักรับแค่ไฟล์ถ้ามีทั้ง URL และ text ในคลิปบอร์ดชุดเดียว — แยกหลายรอบ:
        # Ctrl+V คุณ = text | โปรแกรม Ctrl+V = ไฟล์ | โปรแกรม Ctrl+V = text อีกครั้ง (ลำดับในแชท) → สลับตอน
        if has_text and has_file:
            combined = "\n\n".join(p for k, p in ordered_parts if k == "text")
            mime.setText(combined)
            self._staged_pending_file_paths = [p for k, p in ordered_parts if k == "file"]
            self._staged_plain_text_for_repeat = combined
        elif has_text:
            mime.setText("\n\n".join(p for k, p in ordered_parts if k == "text"))
        elif has_file:
            mime.setUrls([QUrl.fromLocalFile(p) for k, p in ordered_parts if k == "file"])
        else:
            mime.setText("")
        clipboard.setMimeData(mime)

        QTimer.singleShot(100, self._reset_ignore_flag)
        self._update_status()

    def _reset_ignore_flag(self):
        self._ignore_clipboard_change = False

    # ============================================================ STATUS
    def _update_status(self):
        if self.paused:
            return
        self.status_label.setStyleSheet("")
        if self.mode == self.MODE_PASTE:
            if not self.prompt_files or not self.chapter_files:
                self.status_label.setText("-- Select Prompt + Chapter folders --")
                return
            total = len(self.chapter_files)
            chapters_remaining = total - self.current_index
            chapters_to_paste = min(self.concurrent_chapters, chapters_remaining)
            pc = len(self.prompt_files)
            
            if chapters_to_paste == 1:
                ch_label = self._ch_label(self.current_index)
                self.status_label.setText(
                    f"[READY] {pc} Prompt(s) + {ch_label}  ({self.current_index + 1}/{total})"
                )
            else:
                end_idx = self.current_index + chapters_to_paste - 1
                rounds_remaining = (chapters_remaining + self.concurrent_chapters - 1) // self.concurrent_chapters
                ch_label = self._ch_range_label(self.current_index, end_idx)
                self.status_label.setText(
                    f"[READY] {pc} Prompt(s) + {ch_label}  ({self.current_index + 1}-{end_idx + 1}/{total}, {rounds_remaining} rounds left)"
                )
        elif self.mode == self.MODE_COPY:
            if not self.chapter_files:
                self.status_label.setText("-- Select Chapter + Output folders --")
                return
            total = len(self.chapter_files)
            if self.current_index >= total:
                self.status_label.setText("[DONE] All chapters saved")
                return
            chapters_remaining = total - self.current_index
            chapters_waiting = min(self.concurrent_chapters, chapters_remaining)
            if chapters_waiting == 1:
                ch_label = self._ch_label(self.current_index)
                self.status_label.setText(
                    f"[WAITING] Copy text for: {ch_label}  ({self.current_index + 1}/{total})"
                )
            else:
                end_idx = self.current_index + chapters_waiting - 1
                rounds_left = (chapters_remaining + self.concurrent_chapters - 1) // self.concurrent_chapters
                ch_label = self._ch_range_label(self.current_index, end_idx)
                self.status_label.setText(
                    f"[WAITING] Copy text for: {ch_label}  "
                    f"({self.current_index + 1}-{end_idx + 1}/{total}, {rounds_left} saves left)"
                )
        else:  # VOCAB mode
            self.status_label.setText(
                f"[VOCAB MODE] Ready to append entries to vocab.txt (Current: {self.vocab_entry_count} entries)"
            )

    # ============================================================ ACTIONS
    def _on_paste(self):
        if self.mode != self.MODE_PASTE or self.paused or not self.chapter_files:
            return
        if self._staged_sequence_active:
            return

        pending = self._staged_pending_file_paths
        if pending:
            paths = list(pending)
            self._staged_pending_file_paths = None
            self._staged_sequence_active = True
            self._run_staged_file_paste_then_finish(paths)
            return

        self._finish_paste_advance()

    def _run_staged_file_paste_then_finish(self, paths: list[str]):
        """หลังคุณ Ctrl+V วางข้อความแล้ว — ตั้งคลิปบอร์ดเป็นไฟล์แล้ว Ctrl+V สังเคราะห์."""
        self._ignore_clipboard_change = True
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
        QApplication.clipboard().setMimeData(mime)
        QApplication.processEvents()
        ms = max(40, min(self.staged_ms_clipboard_to_ctrl_v, 3000))
        QTimer.singleShot(ms, lambda: self._staged_send_synthetic_ctrl_v(self._staged_after_file_paste_prepare_text))

    def _inject_ctrl_v_windows(self) -> None:
        """สำรอง: keybd_event Ctrl+V (Windows)."""
        if sys.platform != "win32":
            return
        import ctypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        VK_CONTROL = 0x11
        VK_V = 0x56
        KEYEVENTF_KEYUP = 0x0002
        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        kernel32.Sleep(12)
        user32.keybd_event(VK_V, 0, 0, 0)
        kernel32.Sleep(12)
        user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
        kernel32.Sleep(12)
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)

    def _staged_send_synthetic_ctrl_v(self, after_delay=None):
        """ส่ง Ctrl+V สังเคราะห์; หลังดีเลย์เรียก after_delay หรือจบรอบ (_staged_clear_suppress_and_advance)."""
        self._suppress_paste_hotkey = True
        if sys.platform == "win32":
            if not _win32_sendinput_ctrl_v():
                try:
                    self._inject_ctrl_v_windows()
                except Exception:
                    pass
                try:
                    keyboard.send("ctrl+v")
                except Exception:
                    pass
        else:
            try:
                keyboard.send("ctrl+v")
            except Exception:
                pass
        ms = max(50, min(self.staged_ms_after_text_paste, 8000))
        done = after_delay if after_delay is not None else self._staged_clear_suppress_and_advance
        QTimer.singleShot(ms, done)

    def _staged_after_file_paste_prepare_text(self):
        """หลังวางไฟล์แล้ว — คืนข้อความลงคลิปบอร์ดแล้ว Ctrl+V สังเคราะห์รอบสอง."""
        txt = self._staged_plain_text_for_repeat or ""
        mime = QMimeData()
        mime.setText(txt)
        QApplication.clipboard().setMimeData(mime)
        QApplication.processEvents()
        ms = max(40, min(self.staged_ms_clipboard_to_ctrl_v, 3000))
        QTimer.singleShot(ms, self._staged_send_synthetic_text_repeat)

    def _staged_send_synthetic_text_repeat(self):
        self._staged_send_synthetic_ctrl_v()

    def _staged_clear_suppress_and_advance(self):
        self._suppress_paste_hotkey = False
        self._ignore_clipboard_change = False
        self._staged_sequence_active = False
        self._staged_plain_text_for_repeat = None
        self._finish_paste_advance()

    def _finish_paste_advance(self):
        total = len(self.chapter_files)
        chapters_remaining = total - self.current_index
        chapters_pasted = min(self.concurrent_chapters, chapters_remaining)
        pc = len(self.prompt_files)

        if chapters_pasted == 1:
            ch_label = self._ch_label(self.current_index)
            self._show_toast(f"📋 PASTED: {pc} Prompt(s) + {ch_label}", "paste")
        else:
            end_idx = self.current_index + chapters_pasted - 1
            ch_label = self._ch_range_label(self.current_index, end_idx)
            self._show_toast(
                f"📋 PASTED: {pc} Prompt(s) + {ch_label}",
                "paste",
            )

        self.current_index += chapters_pasted

        if self.current_index < len(self.chapter_files):
            self._load_clipboard_paste_mode()
        else:
            self.status_label.setText("[DONE] All chapters pasted")

    def _go_prev(self):
        if not self.chapter_files:
            return
        if self.current_index > 0:
            if self.mode == self.MODE_PASTE:
                # Move back by concurrent_chapters count
                self.current_index = max(0, self.current_index - self.concurrent_chapters)
                self._load_clipboard_paste_mode()
            else:
                # Copy mode: align with paste rounds; vocab: one step
                if self.mode == self.MODE_COPY:
                    self.current_index = max(0, self.current_index - self.concurrent_chapters)
                else:
                    self.current_index -= 1
                self._update_status()

    def _go_next(self):
        if not self.chapter_files:
            return
        if self.current_index < len(self.chapter_files):
            if self.mode == self.MODE_PASTE:
                # Move forward by concurrent_chapters count
                self.current_index = min(len(self.chapter_files) - 1, self.current_index + self.concurrent_chapters)
                self._load_clipboard_paste_mode()
            elif self.mode == self.MODE_COPY:
                self.current_index = min(
                    len(self.chapter_files) - 1,
                    self.current_index + self.concurrent_chapters,
                )
                self._update_status()
            else:
                # Vocab mode: move forward by 1
                if self.current_index < len(self.chapter_files) - 1:
                    self.current_index += 1
                self._update_status()

    def _reset_index(self):
        if not self.chapter_files:
            return
        self.current_index = 0
        self.paused = False
        self.pause_btn.setText("⏸ Pause")
        if self.mode == self.MODE_PASTE:
            self._load_clipboard_paste_mode()
        else:
            self._update_status()

    def _toggle_pause(self):
        self.paused = not self.paused
        if self.paused:
            self.pause_btn.setText("▶ Resume")
            self.status_label.setText("[PAUSED]  Press F12 or Resume to continue")
            self.status_label.setStyleSheet(
                "#status { color: #ffcc00; background: rgba(255,255,255,0.07); "
                "border-radius: 8px; padding: 6px 10px; font-size: 14px; }"
            )
        else:
            self.pause_btn.setText("⏸ Pause")
            self.status_label.setStyleSheet("")
            if self.mode == self.MODE_PASTE:
                self._load_clipboard_paste_mode()
            else:
                self._update_status()

    # ============================================================ MINIMIZE/EXPAND
    def _toggle_minimize(self):
        self.minimized = not self.minimized
        if self.minimized:
            self.content_widget.hide()
            self.minimize_btn.setText("□")
            self.adjustSize()
        else:
            self.content_widget.show()
            self.minimize_btn.setText("−")
            self.adjustSize()

    # ============================================================ TOAST NOTIFICATION
    def _show_toast(self, message: str, action_type: str):
        if self.toast:
            self.toast.close()
        self.toast = ToastNotification(message, action_type)
        self.toast.show()

    # ============================================================ QUIT
    def _quit(self):
        keyboard.unhook_all()
        QApplication.quit()


# ---------------------------------------------------------------------------
# Toast Notification Widget
# ---------------------------------------------------------------------------
class ToastNotification(QWidget):
    def __init__(self, message: str, action_type: str):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 16, 20, 16)
        
        label = QLabel(message)
        label.setObjectName("toastLabel")
        label.setWordWrap(True)
        
        font = QFont("Segoe UI", 14, QFont.Weight.Bold)
        label.setFont(font)
        
        if action_type == "paste":
            bg_color = "rgba(80, 180, 255, 230)"
            text_color = "#ffffff"
        elif action_type == "vocab":
            bg_color = "rgba(180, 100, 255, 230)"
            text_color = "#ffffff"
        else:  # copy
            bg_color = "rgba(100, 220, 100, 230)"
            text_color = "#ffffff"
        
        label.setStyleSheet(f"""
            #toastLabel {{
                color: {text_color};
                padding: 12px 20px;
                background: {bg_color};
                border-radius: 12px;
            }}
        """)
        
        layout.addWidget(label)
        self.setLayout(layout)
        
        screen = QApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)
        
        QTimer.singleShot(2000, self._fade_out)
    
    def _fade_out(self):
        self.effect = QGraphicsOpacityEffect()
        self.setGraphicsEffect(self.effect)
        
        self.fade_timer = QTimer(self)
        self.fade_timer.timeout.connect(self._update_opacity)
        self.opacity = 1.0
        self.fade_timer.start(30)
    
    def _update_opacity(self):
        self.opacity -= 0.05
        if self.opacity <= 0:
            self.fade_timer.stop()
            self.close()
        else:
            self.effect.setOpacity(self.opacity)
    
    def paintEvent(self, event):
        from PyQt6.QtGui import QPainter
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.end()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Match the look of `python inkcopy.py`: prefer native Windows
    # style; only fall back if the platform style plugin is unavailable.
    try:
        from PyQt6.QtWidgets import QStyleFactory
        _keys = [k.lower() for k in QStyleFactory.keys()]
        for _preferred in ("windows11", "windowsvista", "windows"):
            if _preferred in _keys:
                app.setStyle(_preferred)
                break
    except Exception:
        pass
    app.setApplicationName("INKCOPY")
    app.setApplicationDisplayName("INKCOPY")
    if os.path.isfile(ICON_PATH):
        app.setWindowIcon(QIcon(ICON_PATH))
    app.setQuitOnLastWindowClosed(True)
    overlay = SmartClipboardOverlay()
    if os.path.isfile(ICON_PATH):
        overlay.setWindowIcon(QIcon(ICON_PATH))
    sys.exit(app.exec())
