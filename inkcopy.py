from __future__ import annotations

import sys
import os

# Check for required modules before importing
def check_modules():
    missing = []
    # Hotkey backend differs per platform: `keyboard` on Windows, `pynput` elsewhere.
    if sys.platform == "win32":
        try:
            import keyboard  # noqa: F401
        except ImportError:
            missing.append("keyboard")
    else:
        try:
            import pynput  # noqa: F401
        except ImportError:
            missing.append("pynput")
    try:
        import natsort  # noqa: F401
    except ImportError:
        missing.append("natsort")
    try:
        from PyQt6.QtCore import Qt, QUrl, QMimeData, QTimer, pyqtSignal, QObject  # noqa: F401
    except ImportError:
        missing.append("PyQt6")
    if sys.platform == "darwin":
        try:
            import Quartz  # noqa: F401
        except ImportError:
            missing.append("pyobjc-framework-Quartz")

    if missing:
        sep = "\\" if sys.platform == "win32" else "/"
        req_path = os.path.dirname(os.path.abspath(__file__)) + sep + "requirements.txt"
        print("=" * 60)
        print("ERROR: Missing required Python modules!")
        print("=" * 60)
        print(f"\nMissing: {', '.join(missing)}")
        print("\nTo fix, run this command in terminal:")
        print(f"   pip install -r {req_path}")
        print("\nOr install manually:")
        if sys.platform == "win32":
            print("   pip install keyboard natsort PyQt6")
        elif sys.platform == "darwin":
            print("   pip install pynput natsort PyQt6 pyobjc-framework-Cocoa pyobjc-framework-Quartz")
        else:
            print("   pip install pynput natsort PyQt6")
        print("\nPress Enter to exit...")
        input()
        sys.exit(1)

check_modules()

import json
import re
import time
import unicodedata
from pathlib import Path

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

__version__ = "0.2.5"
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
# Diagnostic logger — writes to a per-user log file users can share when
# Mac/Windows hotkeys "look granted" but Cmd+V / Ctrl+V silently fails to fire.
# Path: ~/Library/Logs/INKCOPY/inkcopy.log (Mac) | %APPDATA%\INKCOPY\inkcopy.log (Win)
# Rotates by truncating to last half when it exceeds _LOG_MAX_BYTES.
# ---------------------------------------------------------------------------
def _log_dir() -> str:
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Logs/INKCOPY")
    return CONFIG_DIR


LOG_PATH = os.path.join(_log_dir(), "inkcopy.log")
_LOG_MAX_BYTES = 1_000_000


def _log(msg: str, level: str = "INFO") -> None:
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        try:
            if os.path.isfile(LOG_PATH) and os.path.getsize(LOG_PATH) > _LOG_MAX_BYTES:
                with open(LOG_PATH, "rb") as fh:
                    fh.seek(-(_LOG_MAX_BYTES // 2), 2)
                    tail = fh.read()
                with open(LOG_PATH, "wb") as fh:
                    fh.write(tail)
        except OSError:
            pass
        import datetime
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(f"[{ts}] [{level}] {msg}\n")
    except Exception:
        pass


def _macos_accessibility_trusted() -> bool | None:
    """
    Returns True/False on macOS based on the live TCC check; None on other OSes
    or if the check cannot be performed (no ApplicationServices framework).
    The toggle in System Settings can show "ON" while the underlying TCC entry
    rejects the binary — this calls into AXIsProcessTrusted to see the real state.
    """
    if sys.platform != "darwin":
        return None
    try:
        import ctypes
        import ctypes.util
        lib_path = ctypes.util.find_library("ApplicationServices")
        if not lib_path:
            return None
        lib = ctypes.cdll.LoadLibrary(lib_path)
        lib.AXIsProcessTrusted.restype = ctypes.c_int
        lib.AXIsProcessTrusted.argtypes = []
        return bool(lib.AXIsProcessTrusted())
    except Exception:
        return None


def _macos_input_monitoring_trusted() -> bool | None:
    """
    Best-effort check for the "Input Monitoring" privacy bucket via IOKit's
    IOHIDCheckAccess. Returns True/False/None.

    macOS Catalina+ split Accessibility into two TCC entries:
      • Accessibility   — required to *synthesize* events (CGEventPost / pynput)
      • Input Monitoring — required to *observe* events from other apps
                          (CGEventTap, in some macOS versions also affects
                          NSEvent's global key monitor)

    A user toggling only one and reporting "permission ON" is the most common
    source of "Cmd+V silently fails" reports, so surface it explicitly.

    kIOHIDRequestTypeListenEvent = 1
    kIOHIDAccessTypeGranted      = 0
    """
    if sys.platform != "darwin":
        return None
    try:
        import ctypes
        import ctypes.util
        lib_path = ctypes.util.find_library("IOKit")
        if not lib_path:
            return None
        lib = ctypes.cdll.LoadLibrary(lib_path)
        if not hasattr(lib, "IOHIDCheckAccess"):
            return None
        lib.IOHIDCheckAccess.restype = ctypes.c_uint32
        lib.IOHIDCheckAccess.argtypes = [ctypes.c_uint32]
        result = int(lib.IOHIDCheckAccess(1))
        if result == 0:
            return True
        if result == 1:
            return False
        return None
    except Exception:
        return None


_AX_PROMPTED = False


def _macos_prompt_accessibility() -> bool | None:
    """Trigger the macOS "grant Accessibility" system dialog (once per run).

    Without Accessibility/Input Monitoring the global key listener registers
    successfully but silently receives zero events — the #1 reason INKCOPY
    "looks broken" on macOS. AXIsProcessTrustedWithOptions with the prompt key
    asks the OS to show its own grant dialog; it is non-blocking and a no-op if
    already trusted. Returns the trusted state, or None off-darwin / on failure.
    """
    global _AX_PROMPTED
    if sys.platform != "darwin":
        return None
    if _AX_PROMPTED:
        return _macos_accessibility_trusted()
    _AX_PROMPTED = True
    try:
        from ApplicationServices import (
            AXIsProcessTrustedWithOptions,
            kAXTrustedCheckOptionPrompt,
        )
        trusted = bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True}))
        _log(f"AX prompt shown (trusted={trusted})")
        return trusted
    except Exception as exc:
        _log(f"AX prompt failed: {exc}", "WARN")
        return _macos_accessibility_trusted()


def _macos_make_floating_overlay(widget) -> None:
    """Keep a frameless overlay visible above other apps on macOS.

    Qt.WindowType.Tool maps to an NSPanel whose hidesOnDeactivate defaults to
    YES, so the overlay VANISHES whenever another app (e.g. Chrome) becomes
    frontmost — which is precisely when INKCOPY needs to stay on screen. Force
    the native window to stay put, float above normal windows, and join every
    Space (incl. a fullscreen browser). No-op off darwin / on failure.
    """
    if sys.platform != "darwin":
        return
    # Only the real Cocoa platform has an NSWindow behind winId(); under the
    # offscreen/minimal QPA plugins winId() is NOT an NSView pointer, so
    # wrapping it and calling -window would dereference garbage and crash the
    # process (a native segfault no try/except can catch).
    if QApplication.platformName() != "cocoa":
        return
    try:
        import objc
        from AppKit import (
            NSScreenSaverWindowLevel,
            NSWindowCollectionBehaviorCanJoinAllSpaces,
            NSWindowCollectionBehaviorFullScreenAuxiliary,
            NSWindowCollectionBehaviorIgnoresCycle,
            NSWindowCollectionBehaviorStationary,
        )

        view = objc.objc_object(c_void_p=int(widget.winId()))
        win = view.window()
        if win is None:
            return
        win.setHidesOnDeactivate_(False)
        # Screen-saver level (1000) is high enough to sit above another app's
        # FULLSCREEN window — status (25) and floating (3) were composited below
        # the fullscreen Space, so the overlay only showed on the desktop Space.
        win.setLevel_(NSScreenSaverWindowLevel)
        win.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorStationary
            | NSWindowCollectionBehaviorFullScreenAuxiliary
            | NSWindowCollectionBehaviorIgnoresCycle
        )
    except Exception as exc:
        _log(f"macOS overlay window config failed: {exc}", "WARN")


def _macos_set_accessory_policy() -> None:
    """Run INKCOPY as a background 'accessory' app on macOS so the overlay can
    float over OTHER apps' native-fullscreen Spaces.

    A regular (Dock-icon) app's windows are NEVER admitted to another app's
    fullscreen Space, regardless of window level — that's why screen-saver level
    + canJoinAllSpaces alone wasn't enough. Only an accessory/agent app can.
    Tradeoff: no Dock icon and no Cmd-Tab entry (quit via the overlay's ✕).
    No-op off the real cocoa platform (avoids touching a non-existent NSApp).
    """
    if sys.platform != "darwin":
        return
    try:
        if QApplication.platformName() != "cocoa":
            return
        from AppKit import (
            NSApplication,
            NSApplicationActivationPolicyAccessory,
        )

        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory
        )
        _log("macOS activation policy set to accessory (overlay floats over fullscreen)")
    except Exception as exc:
        _log(f"macOS accessory policy failed: {exc}", "WARN")


def _running_from_macos_dmg() -> bool:
    """
    True if the frozen .app is being run directly from a mounted DMG.
    TCC is unreliable for DMG-mounted bundles — the user must drag
    INKCOPY.app into /Applications/ for permissions to stick.
    """
    if sys.platform != "darwin":
        return False
    if not getattr(sys, "frozen", False):
        return False
    return "/Volumes/" in (sys.executable or "")


# ---------------------------------------------------------------------------
# macOS synthetic Cmd+V via Quartz CGEventPost.
# pynput's Controller works in most cases but is unreliable on Sonoma+
# (CGEventCreateKeyboardEvent vs the deprecated path it uses). Using
# CGEventPost directly is what Apple itself recommends and what every
# automation tool (Karabiner, Hammerspoon) standardised on.
# ---------------------------------------------------------------------------
_QUARTZ_LIB = None


def _quartz_lib():
    global _QUARTZ_LIB
    if _QUARTZ_LIB is not None or sys.platform != "darwin":
        return _QUARTZ_LIB
    try:
        import ctypes
        import ctypes.util
        path = ctypes.util.find_library("ApplicationServices")
        if not path:
            return None
        lib = ctypes.cdll.LoadLibrary(path)
        lib.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
        lib.CGEventCreateKeyboardEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_bool]
        lib.CGEventSetFlags.restype = None
        lib.CGEventSetFlags.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
        lib.CGEventPost.restype = None
        lib.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
        lib.CFRelease.restype = None
        lib.CFRelease.argtypes = [ctypes.c_void_p]
        _QUARTZ_LIB = lib
    except Exception as exc:
        _QUARTZ_LIB = None
    return _QUARTZ_LIB


def _cg_send_cmd_v() -> bool:
    """Synthesize Cmd down → V down → V up → Cmd up via Quartz."""
    if sys.platform != "darwin":
        return False
    lib = _quartz_lib()
    if lib is None:
        return False
    try:
        kCGHIDEventTap = 0
        kCGEventFlagMaskCommand = 1 << 20
        VK_V = 9  # Carbon virtual keycode for V
        ev_down = lib.CGEventCreateKeyboardEvent(None, VK_V, True)
        if not ev_down:
            return False
        ev_up = lib.CGEventCreateKeyboardEvent(None, VK_V, False)
        if not ev_up:
            lib.CFRelease(ev_down)
            return False
        try:
            lib.CGEventSetFlags(ev_down, kCGEventFlagMaskCommand)
            lib.CGEventSetFlags(ev_up, kCGEventFlagMaskCommand)
            lib.CGEventPost(kCGHIDEventTap, ev_down)
            lib.CGEventPost(kCGHIDEventTap, ev_up)
        finally:
            lib.CFRelease(ev_down)
            lib.CFRelease(ev_up)
        return True
    except Exception as exc:
        _log(f"CGEventPost Cmd+V failed: {exc}", "ERROR")
        return False


_log(f"==== INKCOPY {__version__} starting on {sys.platform} ====")
_log(f"frozen={getattr(sys, 'frozen', False)} executable={sys.executable}")
_log(f"config={CONFIG_PATH}")
_log(f"log={LOG_PATH}")
if sys.platform == "darwin":
    _log(f"macOS Accessibility trusted: {_macos_accessibility_trusted()}")
    _log(f"macOS Input Monitoring trusted: {_macos_input_monitoring_trusted()}")
    if _running_from_macos_dmg():
        _log(
            "Running from /Volumes/ (DMG). macOS TCC will likely refuse to grant "
            "hotkey permissions reliably. Drag INKCOPY.app to /Applications/ and "
            "re-grant Accessibility + Input Monitoring there.",
            "WARN",
        )


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
# Windows: native clipboard text writer (CF_UNICODETEXT)
#   Qt's QClipboard.setMimeData() uses OleSetClipboard, which can silently FAIL
#   (CLIPBRD_E_CANT_OPEN) when the app we just pasted into still holds the
#   clipboard open. In mixed paste mode the clipboard flips text -> files ->
#   text within ~0.5s, so one lost text write leaves stale FILE data and the
#   next real Ctrl+V pastes files instead of text (files stack, chapter text
#   missing). SetClipboardData with an OpenClipboard retry loop survives that.
#   NOTE: file writes deliberately stay on the existing Qt path — they already
#   work — so this change only hardens the text write.
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
    # Correct restypes are essential on 64-bit: handles/pointers are 64-bit and
    # ctypes defaults to c_int, which would truncate them and corrupt/crash.
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.restype = wintypes.HGLOBAL
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]

    opened = False
    for _ in range(40):
        if user32.OpenClipboard(None):
            opened = True
            break
        kernel32.Sleep(25)
    if not opened:
        _log("win32 clipboard: OpenClipboard failed after retries", "ERROR")
        return False
    wrote = False
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
        # On success the system owns h_mem — do NOT free it.
        if not user32.SetClipboardData(CF_UNICODETEXT, h_mem):
            kernel32.GlobalFree(h_mem)
            return False
        wrote = True
    finally:
        user32.CloseClipboard()
    # Post-verify (clipboard now closed): confirm TEXT actually landed and no
    # stale FILE data lingered. This is what catches the "files stay, text
    # missing" failure — we report False so the caller can retry.
    if not wrote:
        return False
    if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
        _log("win32 clipboard: CF_UNICODETEXT not present after write", "ERROR")
        return False
    return True


def _win32_set_clipboard_files(paths: list[str]) -> bool:
    """Write a CF_HDROP file list to the clipboard natively (Windows).

    This is the SAME clipboard format Qt's setUrls() produces for local files,
    so the target app (Gemini/Chrome) sees no difference — but routing it through
    the native API keeps clipboard *ownership* consistent with the native text
    write. Previously files went through Qt (OleSetClipboard) while text went
    native (SetClipboardData); the two ownership models fought under the rapid
    text→file→text swaps of mixed paste, so a write could land silently stale
    and leave FILE data on the clipboard → the next real Ctrl+V pasted files
    (stacking) and the chapter text never appeared. One mechanism = no fight.
    """
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    CF_HDROP = 15
    GHND = 0x0042  # GMEM_MOVEABLE | GMEM_ZEROINIT
    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.restype = wintypes.HGLOBAL
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]

    valid = [os.path.abspath(p) for p in paths if os.path.exists(p)]
    if not valid:
        _log("win32 clipboard: no existing files to write to CF_HDROP", "WARN")
        return False

    class _DROPFILES(ctypes.Structure):
        _fields_ = [
            ("pFiles", wintypes.DWORD),  # offset to the file list
            ("pt_x", wintypes.LONG),
            ("pt_y", wintypes.LONG),
            ("fNC", wintypes.BOOL),
            ("fWide", wintypes.BOOL),    # TRUE → wide (UTF-16) file names
        ]

    header = _DROPFILES()
    header_size = ctypes.sizeof(_DROPFILES)
    header.pFiles = header_size
    header.fWide = 1
    # File list: each path NUL-terminated, whole list double-NUL terminated.
    files_blob = ("".join(p + "\0" for p in valid) + "\0").encode("utf-16-le")
    total = header_size + len(files_blob)

    opened = False
    for _ in range(40):
        if user32.OpenClipboard(None):
            opened = True
            break
        kernel32.Sleep(25)
    if not opened:
        _log("win32 clipboard(files): OpenClipboard failed after retries", "ERROR")
        return False
    wrote = False
    try:
        if not user32.EmptyClipboard():
            return False
        h_mem = kernel32.GlobalAlloc(GHND, total)
        if not h_mem:
            return False
        ptr = kernel32.GlobalLock(h_mem)
        if not ptr:
            kernel32.GlobalFree(h_mem)
            return False
        try:
            ctypes.memmove(ptr, ctypes.byref(header), header_size)
            ctypes.memmove(ptr + header_size, files_blob, len(files_blob))
        finally:
            kernel32.GlobalUnlock(h_mem)
        if not user32.SetClipboardData(CF_HDROP, h_mem):
            kernel32.GlobalFree(h_mem)
            return False
        wrote = True
    finally:
        user32.CloseClipboard()
    if not wrote:
        return False
    if not user32.IsClipboardFormatAvailable(CF_HDROP):
        _log("win32 clipboard: CF_HDROP not present after write", "ERROR")
        return False
    return True


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
# macOS clipboard helpers
#   Qt's QMimeData.setUrls() works in most cases, but Chrome/Gemini sometimes
#   ignores Qt-written file URLs because Qt6 still writes the legacy
#   NSURLPboardType. Writing NSURL objects via NSPasteboard.writeObjects_()
#   produces "public.file-url" entries that every macOS browser recognises.
# ---------------------------------------------------------------------------
def _macos_pasteboard_types(pb) -> list[str]:
    try:
        return [str(t) for t in (pb.types() or [])]
    except Exception:
        return []


def _set_macos_clipboard_files(paths: list[str]) -> bool:
    if sys.platform != "darwin":
        return False
    try:
        from AppKit import NSPasteboard, NSURL
        pb = NSPasteboard.generalPasteboard()
        before = int(pb.changeCount())
        pb.clearContents()
        urls = []
        for p in paths:
            if os.path.exists(p):
                urls.append(NSURL.fileURLWithPath_(p))
            else:
                _log(f"NSPasteboard skip missing file: {p}", "WARN")
        if not urls:
            return False
        ok = bool(pb.writeObjects_(urls))
        after = int(pb.changeCount())
        types = _macos_pasteboard_types(pb)
        verified = ok and after != before and any(
            t in types
            for t in ("public.file-url", "NSFilenamesPboardType", "Apple URL pasteboard type")
        )
        _log(
            f"NSPasteboard wrote {len(urls)} file URL(s) "
            f"(ok={ok}, verified={verified}, change={before}->{after}, types={types})"
        )
        return verified
    except Exception as exc:
        _log(f"NSPasteboard file write failed: {exc}", "ERROR")
        return False


def _set_macos_clipboard_text(text: str) -> bool:
    if sys.platform != "darwin":
        return False
    try:
        from AppKit import NSPasteboard, NSPasteboardTypeString
        pb = NSPasteboard.generalPasteboard()
        before = int(pb.changeCount())
        pb.clearContents()
        ok = bool(pb.setString_forType_(text, NSPasteboardTypeString))
        after = int(pb.changeCount())
        readback = pb.stringForType_(NSPasteboardTypeString) or ""
        verified = ok and after != before and str(readback) == text
        _log(
            f"NSPasteboard wrote text ({len(text)} chars, ok={ok}, "
            f"verified={verified}, change={before}->{after}, types={_macos_pasteboard_types(pb)})"
        )
        return verified
    except Exception as exc:
        _log(f"NSPasteboard text write failed: {exc}", "ERROR")
        return False


def _set_clipboard_text_native(text: str) -> bool:
    """Write text to the clipboard via the OS-native API (reliable under the
    rapid clipboard swaps of mixed paste). Returns False on Linux / failure so
    callers fall back to Qt's QClipboard."""
    if sys.platform == "darwin":
        return _set_macos_clipboard_text(text)
    if sys.platform == "win32":
        # Self-verifying write + a couple of retries: if the target app still
        # holds the clipboard open (post-paste), the first attempt can fail —
        # retrying after a short sleep wins instead of silently leaving stale
        # data behind.
        import ctypes
        for _attempt in range(3):
            if _win32_set_clipboard_unicode(text):
                return True
            ctypes.windll.kernel32.Sleep(20)
        return False
    return False


def _set_clipboard_files_native(paths: list[str]) -> bool:
    """Write a file list to the clipboard via the OS-native API.
    macOS → NSPasteboard file URLs; Windows → CF_HDROP. Returns False on
    Linux / failure so callers fall back to Qt's QClipboard.setUrls()."""
    if sys.platform == "darwin":
        return _set_macos_clipboard_files(paths)
    if sys.platform == "win32":
        import ctypes
        for _attempt in range(3):
            if _win32_set_clipboard_files(paths):
                return True
            ctypes.windll.kernel32.Sleep(20)
        return False
    return False


# ---------------------------------------------------------------------------
# Cross-platform hotkey backend
#   Windows: `keyboard` library (low-latency Win32 hooks; existing behavior).
#   macOS / Linux: `pynput` (works with Quartz on macOS — needs Accessibility).
# Backend exposes: register / unregister / send_paste / is_paste_modifier_held.
# Modifier is Ctrl on Windows/Linux, Cmd on macOS.
# ---------------------------------------------------------------------------
PASTE_MODIFIER_NAME = "Cmd" if sys.platform == "darwin" else "Ctrl"


class _HotkeyBackend:
    def register(self, on_paste, on_prev, on_next, on_pause): ...
    def unregister(self): ...
    def send_paste(self) -> bool: ...
    def is_paste_modifier_held(self) -> bool: ...


if sys.platform == "win32":
    import keyboard as _kb_lib

    class _KeyboardLibBackend(_HotkeyBackend):
        def __init__(self):
            self._registered = False
            self._on_paste = None
            self.stats = {
                "keys_received": 0,
                "v_keys_seen": 0,
                "modifier_events": 0,
                "paste_fires": 0,
                "prev_fires": 0,
                "next_fires": 0,
                "pause_fires": 0,
                "last_key_repr": "",
                "last_error": "",
                "listener_started": False,
            }

        def register(self, on_paste, on_prev, on_next, on_pause):
            if self._registered:
                return
            self._on_paste = on_paste
            try:
                _kb_lib.on_press_key("v", self._handle_v, suppress=False)
                _kb_lib.add_hotkey("f9", lambda: (self.stats.__setitem__("prev_fires", self.stats["prev_fires"] + 1), _log("F9 → prev"), on_prev()))
                _kb_lib.add_hotkey("f10", lambda: (self.stats.__setitem__("next_fires", self.stats["next_fires"] + 1), _log("F10 → next"), on_next()))
                _kb_lib.add_hotkey("f12", lambda: (self.stats.__setitem__("pause_fires", self.stats["pause_fires"] + 1), _log("F12 → pause"), on_pause()))
                self._registered = True
                self.stats["listener_started"] = True
                _log("keyboard hooks installed")
            except Exception as exc:
                import traceback
                self.stats["last_error"] = f"register: {exc}"
                _log(f"keyboard register FAILED: {exc}\n{traceback.format_exc()}", "ERROR")

        def _handle_v(self, _event):
            self.stats["keys_received"] += 1
            self.stats["v_keys_seen"] += 1
            held = self.is_paste_modifier_held()
            if held:
                self.stats["paste_fires"] += 1
                _log("Ctrl+V → paste fire")
            if self._on_paste is not None and held:
                self._on_paste()

        def unregister(self):
            try:
                _kb_lib.unhook_all()
            except Exception:
                pass
            self._registered = False
            self.stats["listener_started"] = False

        def is_alive(self) -> bool:
            return self._registered

        def send_paste(self) -> bool:
            try:
                _kb_lib.send("ctrl+v")
                return True
            except Exception as exc:
                _log(f"send_paste error: {exc}", "ERROR")
                return False

        def is_paste_modifier_held(self) -> bool:
            try:
                return _kb_lib.is_pressed("ctrl")
            except Exception:
                return False

    _hotkey_backend: _HotkeyBackend = _KeyboardLibBackend()

else:
    from pynput import keyboard as _pynkb

    class _PynputBackend(_HotkeyBackend):
        # macOS V keycode is 9, Windows VK_V is 0x56. Use both char and vk for safety:
        # when Cmd/Ctrl is held, pynput sometimes returns a KeyCode without a populated char.
        _V_VKS = {9, 0x56, 47}  # 47 covers some Linux X11 layouts

        def __init__(self):
            self._listener = None
            self._mods: set[str] = set()
            self._controller = _pynkb.Controller()
            self._on_paste = None
            self._on_prev = None
            self._on_next = None
            self._on_pause = None
            # Diagnostics counters — surfaced in the Diagnostics row + log.
            self.stats = {
                "keys_received": 0,
                "v_keys_seen": 0,
                "modifier_events": 0,
                "paste_fires": 0,
                "prev_fires": 0,
                "next_fires": 0,
                "pause_fires": 0,
                "last_key_repr": "",
                "last_error": "",
                "listener_started": False,
            }

        def register(self, on_paste, on_prev, on_next, on_pause):
            if self._listener is not None:
                return
            self._on_paste = on_paste
            self._on_prev = on_prev
            self._on_next = on_next
            self._on_pause = on_pause
            try:
                self._listener = _pynkb.Listener(
                    on_press=self._on_key_press,
                    on_release=self._on_key_release,
                )
                self._listener.daemon = True
                self._listener.start()
                self.stats["listener_started"] = True
                _log("pynput Listener started")
            except Exception as exc:
                import traceback
                self.stats["last_error"] = f"start: {exc}"
                _log(f"pynput Listener start FAILED: {exc}\n{traceback.format_exc()}", "ERROR")
                self._listener = None

        def unregister(self):
            if self._listener is not None:
                try:
                    self._listener.stop()
                except Exception:
                    pass
                self._listener = None
            self._mods.clear()
            self.stats["listener_started"] = False

        def is_alive(self) -> bool:
            return self._listener is not None and self._listener.is_alive()

        def _mod_name(self, key) -> str | None:
            if key in (_pynkb.Key.cmd, _pynkb.Key.cmd_l, _pynkb.Key.cmd_r):
                return "cmd"
            if key in (_pynkb.Key.ctrl, _pynkb.Key.ctrl_l, _pynkb.Key.ctrl_r):
                return "ctrl"
            return None

        def _is_v_key(self, key) -> bool:
            ch = getattr(key, "char", None)
            if ch and ch.lower() == "v":
                return True
            vk = getattr(key, "vk", None)
            if vk is not None and vk in self._V_VKS:
                return True
            return False

        def _key_repr_for_log(self, key) -> str:
            """Compact repr — never logs raw char (privacy). Only flags + vk."""
            vk = getattr(key, "vk", None)
            has_char = getattr(key, "char", None) is not None
            name = getattr(key, "name", None)
            if name:
                return f"Key.{name}"
            return f"KeyCode(vk={vk}, has_char={has_char})"

        def _on_key_press(self, key):
            try:
                self.stats["keys_received"] += 1
                self.stats["last_key_repr"] = self._key_repr_for_log(key)
                mod = self._mod_name(key)
                if mod is not None:
                    self._mods.add(mod)
                    self.stats["modifier_events"] += 1
                    _log(f"mod down: {mod} (held now: {sorted(self._mods)})")
                    return
                if key == _pynkb.Key.f9 and self._on_prev:
                    self.stats["prev_fires"] += 1
                    _log("F9 → prev")
                    self._on_prev()
                    return
                if key == _pynkb.Key.f10 and self._on_next:
                    self.stats["next_fires"] += 1
                    _log("F10 → next")
                    self._on_next()
                    return
                if key == _pynkb.Key.f12 and self._on_pause:
                    self.stats["pause_fires"] += 1
                    _log("F12 → pause")
                    self._on_pause()
                    return
                if self._is_v_key(key):
                    self.stats["v_keys_seen"] += 1
                    held = self.is_paste_modifier_held()
                    _log(f"V key seen — paste_mod_held={held} mods={sorted(self._mods)} repr={self.stats['last_key_repr']}")
                    if held and self._on_paste:
                        self.stats["paste_fires"] += 1
                        _log("Cmd/Ctrl+V → paste fire")
                        self._on_paste()
            except Exception as exc:
                self.stats["last_error"] = f"on_press: {exc}"
                _log(f"on_press error: {exc}", "ERROR")

        def _on_key_release(self, key):
            mod = self._mod_name(key)
            if mod is not None:
                self._mods.discard(mod)

        def is_paste_modifier_held(self) -> bool:
            target = "cmd" if sys.platform == "darwin" else "ctrl"
            return target in self._mods

        def send_paste(self) -> bool:
            # Prefer Quartz CGEventPost on macOS — pynput Controller is unreliable
            # on Sonoma+ (silently no-ops in browser contexts).
            if sys.platform == "darwin" and _cg_send_cmd_v():
                return True
            mod = _pynkb.Key.cmd if sys.platform == "darwin" else _pynkb.Key.ctrl
            try:
                with self._controller.pressed(mod):
                    self._controller.press("v")
                    self._controller.release("v")
                return True
            except Exception as exc:
                _log(f"send_paste error: {exc}", "ERROR")
                return False

    if sys.platform == "darwin":
        # pynput's listener runs in a background thread and calls
        # TSMGetInputSourceProperty (a main-thread-only macOS API). On Sonoma+
        # this trips libdispatch's queue assertion and tears down the whole
        # process — typically right after AppKit refreshes input sources (e.g.
        # when an NSOpenPanel opens). The same race also causes Cmd+V to be
        # missed silently before the crash.
        #
        # Replace it with an AppKit global event monitor: AppKit dispatches the
        # handler on the main thread, observes key events in OTHER apps (which
        # is exactly our use case — INKCOPY is a background overlay), and
        # never touches TSM from a worker thread.
        try:
            from AppKit import NSEvent  # type: ignore
            _NSEVENT_AVAILABLE = True
        except Exception as _exc:
            _log(f"AppKit import failed, falling back to pynput: {_exc}", "WARN")
            _NSEVENT_AVAILABLE = False
        try:
            from Quartz import (  # type: ignore
                CGEventGetFlags,
                CGEventGetIntegerValueField,
                CGEventTapCreate,
                CGEventTapEnable,
                CFMachPortCreateRunLoopSource,
                CFRunLoopAddSource,
                CFRunLoopGetMain,
                kCFRunLoopCommonModes,
                kCGEventFlagMaskCommand,
                kCGEventKeyDown,
                kCGEventTapDisabledByTimeout,
                kCGEventTapDisabledByUserInput,
                kCGEventTapOptionListenOnly,
                kCGHeadInsertEventTap,
                kCGKeyboardEventKeycode,
                kCGSessionEventTap,
            )
            _QUARTZ_EVENT_TAP_AVAILABLE = True
        except Exception as _exc:
            _log(f"Quartz event tap import failed: {_exc}", "WARN")
            _QUARTZ_EVENT_TAP_AVAILABLE = False

        # NSEvent mask for keyDown — explicit value keeps this independent of
        # PyObjC enum versions.
        _NS_EVENT_MASK_KEY_DOWN = 1 << 10
        _NS_CMD_KEY_MASK = 1 << 20  # NSEventModifierFlagCommand

        # Carbon virtual keycodes (Events.h).
        _MAC_KC_V = 9
        _MAC_KC_F9 = 101
        _MAC_KC_F10 = 109
        _MAC_KC_F12 = 111

        class _MacNSEventBackend(_HotkeyBackend):
            def __init__(self):
                self._monitor = None
                self._event_tap = None
                self._event_tap_source = None
                self._event_tap_callback = None
                # Live cmd-held state is queried from NSEvent.modifierFlags(),
                # which always reflects the actual hardware state.
                self._controller = _pynkb.Controller()
                # Dedup window: the NSEvent global monitor AND the CGEventTap both
                # observe the same physical key press and BOTH call _handle_keycode.
                # Without this, one Cmd+V / F9 / F10 / F12 fires its action twice —
                # double-advancing chapters / double-stepping navigation on macOS.
                # Two observers deliver the same press within a few ms; 60ms safely
                # collapses the duplicate while never swallowing a real re-press.
                self._dedup_window_s = 0.06
                self._last_action_ts: dict[int, float] = {}
                self._on_paste = None
                self._on_prev = None
                self._on_next = None
                self._on_pause = None
                self.stats = {
                    "keys_received": 0,
                    "v_keys_seen": 0,
                    "modifier_events": 0,
                    "paste_fires": 0,
                    "prev_fires": 0,
                    "next_fires": 0,
                    "pause_fires": 0,
                    "last_key_repr": "",
                    "last_error": "",
                    "listener_started": False,
                    "event_tap_started": False,
                }

            def register(self, on_paste, on_prev, on_next, on_pause):
                if self._monitor is not None or self._event_tap is not None:
                    return
                self._on_paste = on_paste
                self._on_prev = on_prev
                self._on_next = on_next
                self._on_pause = on_pause
                if not _NSEVENT_AVAILABLE and not _QUARTZ_EVENT_TAP_AVAILABLE:
                    self.stats["last_error"] = "AppKit unavailable"
                    _log("AppKit/NSEvent and Quartz event tap unavailable — hotkeys disabled", "ERROR")
                    return
                if _NSEVENT_AVAILABLE:
                    try:
                        self._monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                            _NS_EVENT_MASK_KEY_DOWN, self._handle_key_event
                        )
                        self.stats["listener_started"] = self._monitor is not None
                        _log(f"NSEvent global monitor started (handle={self._monitor})")
                    except Exception as exc:
                        import traceback
                        self.stats["last_error"] = f"register: {exc}"
                        _log(f"NSEvent monitor FAILED: {exc}\n{traceback.format_exc()}", "ERROR")
                        self._monitor = None
                self._start_event_tap()

            def _start_event_tap(self):
                if self._event_tap is not None or not _QUARTZ_EVENT_TAP_AVAILABLE:
                    return
                try:
                    mask = 1 << int(kCGEventKeyDown)

                    def _tap_callback(proxy, event_type, event, refcon):
                        try:
                            et = int(event_type)
                            if et in (
                                int(kCGEventTapDisabledByTimeout),
                                int(kCGEventTapDisabledByUserInput),
                            ):
                                try:
                                    CGEventTapEnable(self._event_tap, True)
                                    _log("CGEventTap re-enabled")
                                except Exception as exc:
                                    _log(f"CGEventTap re-enable failed: {exc}", "ERROR")
                                return event
                            if et == int(kCGEventKeyDown):
                                kc = int(CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode))
                                flags = int(CGEventGetFlags(event))
                                cmd_held = bool(flags & int(kCGEventFlagMaskCommand))
                                self.stats["keys_received"] += 1
                                self.stats["last_key_repr"] = f"tap kc={kc} cmd={cmd_held} flags=0x{flags:x}"
                                _log(f"CGEventTap keyDown kc={kc} cmd={cmd_held} flags=0x{flags:x}")
                                self._handle_keycode(kc, cmd_held, "CGEventTap")
                        except Exception as exc:
                            self.stats["last_error"] = f"tap: {exc}"
                            _log(f"CGEventTap handler error: {exc}", "ERROR")
                        return event

                    self._event_tap_callback = _tap_callback
                    self._event_tap = CGEventTapCreate(
                        kCGSessionEventTap,
                        kCGHeadInsertEventTap,
                        kCGEventTapOptionListenOnly,
                        mask,
                        self._event_tap_callback,
                        None,
                    )
                    if self._event_tap is None:
                        self.stats["event_tap_started"] = False
                        _log("CGEventTapCreate returned None — check Input Monitoring permission", "ERROR")
                        return
                    self._event_tap_source = CFMachPortCreateRunLoopSource(None, self._event_tap, 0)
                    CFRunLoopAddSource(CFRunLoopGetMain(), self._event_tap_source, kCFRunLoopCommonModes)
                    CGEventTapEnable(self._event_tap, True)
                    self.stats["event_tap_started"] = True
                    _log(f"CGEventTap started (tap={self._event_tap})")
                except Exception as exc:
                    import traceback
                    self.stats["last_error"] = f"tap_register: {exc}"
                    self.stats["event_tap_started"] = False
                    _log(f"CGEventTap FAILED: {exc}\n{traceback.format_exc()}", "ERROR")
                    self._event_tap = None
                    self._event_tap_source = None

            def _handle_key_event(self, event):
                try:
                    self.stats["keys_received"] += 1
                    kc = int(event.keyCode())
                    flags = int(event.modifierFlags())
                    cmd_held = bool(flags & _NS_CMD_KEY_MASK)
                    self.stats["last_key_repr"] = f"kc={kc} cmd={cmd_held} flags=0x{flags:x}"
                    # Verbose per-key trace so users can confirm the monitor
                    # actually receives events (the #1 macOS failure mode is
                    # "permission appears ON but no events ever arrive").
                    _log(f"NSEvent keyDown kc={kc} cmd={cmd_held} flags=0x{flags:x}")
                    self._handle_keycode(kc, cmd_held, "NSEvent")
                except Exception as exc:
                    self.stats["last_error"] = f"handle: {exc}"
                    _log(f"NSEvent handler error: {exc}", "ERROR")

            def _handle_keycode(self, kc: int, cmd_held: bool, source: str):
                try:
                    # Collapse the duplicate the second observer (NSEvent monitor /
                    # CGEventTap) reports for the same physical press. Only the
                    # actionable keys are deduped, keyed by keycode.
                    is_action = (
                        (kc == _MAC_KC_V and cmd_held)
                        or kc in (_MAC_KC_F9, _MAC_KC_F10, _MAC_KC_F12)
                    )
                    if is_action:
                        now = time.monotonic()
                        last = self._last_action_ts.get(kc, 0.0)
                        if (now - last) < self._dedup_window_s:
                            _log(
                                f"deduped duplicate key kc={kc} from {source} "
                                f"({(now - last) * 1000:.0f}ms since last)"
                            )
                            return
                        self._last_action_ts[kc] = now
                    if kc == _MAC_KC_V:
                        self.stats["v_keys_seen"] += 1
                        if cmd_held:
                            self.stats["paste_fires"] += 1
                            _log(f"Cmd+V → paste fire ({source})")
                            if self._on_paste is not None:
                                self._on_paste()
                    elif kc == _MAC_KC_F9 and self._on_prev is not None:
                        self.stats["prev_fires"] += 1
                        _log(f"F9 → prev ({source})")
                        self._on_prev()
                    elif kc == _MAC_KC_F10 and self._on_next is not None:
                        self.stats["next_fires"] += 1
                        _log(f"F10 → next ({source})")
                        self._on_next()
                    elif kc == _MAC_KC_F12 and self._on_pause is not None:
                        self.stats["pause_fires"] += 1
                        _log(f"F12 → pause ({source})")
                        self._on_pause()
                except Exception as exc:
                    self.stats["last_error"] = f"handle: {exc}"
                    _log(f"{source} key handler error: {exc}", "ERROR")

            def unregister(self):
                if self._monitor is not None:
                    try:
                        NSEvent.removeMonitor_(self._monitor)
                    except Exception:
                        pass
                    self._monitor = None
                if self._event_tap is not None:
                    try:
                        CGEventTapEnable(self._event_tap, False)
                    except Exception:
                        pass
                    self._event_tap = None
                    self._event_tap_source = None
                self.stats["listener_started"] = False
                self.stats["event_tap_started"] = False

            def is_alive(self) -> bool:
                return self._monitor is not None or self._event_tap is not None

            def is_paste_modifier_held(self) -> bool:
                if not _NSEVENT_AVAILABLE:
                    return False
                try:
                    return bool(int(NSEvent.modifierFlags()) & _NS_CMD_KEY_MASK)
                except Exception:
                    return False

            def send_paste(self) -> bool:
                # Prefer Quartz CGEventPost — pynput Controller is unreliable on
                # macOS Sonoma+ because Apple changed CGEventCreateKeyboardEvent
                # behavior for assistive use, and pynput's translation layer
                # silently no-ops in some app contexts (especially Electron-based
                # browsers like Chrome/Gemini).
                if _cg_send_cmd_v():
                    _log("send_paste: CGEventPost ok")
                    return True
                _log("send_paste: CGEventPost failed, trying pynput", "WARN")
                try:
                    with self._controller.pressed(_pynkb.Key.cmd):
                        self._controller.press("v")
                        self._controller.release("v")
                    _log("send_paste: pynput ok")
                    return True
                except Exception as exc:
                    _log(f"send_paste error: {exc}", "ERROR")
                    return False

        _hotkey_backend: _HotkeyBackend = (
            _MacNSEventBackend() if _NSEVENT_AVAILABLE else _PynputBackend()
        )
    else:
        _hotkey_backend: _HotkeyBackend = _PynputBackend()


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

        # macOS: become a background accessory app so the overlay can float over
        # other apps' fullscreen Spaces (see _macos_set_accessory_policy).
        _macos_set_accessory_policy()

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
        # macOS has no OS pasteboard-changed notification and Qt's QClipboard
        # .dataChanged often never fires while a non-activating Tool overlay sits
        # in the background — which is the entire COPY/VOCAB use case (user copies
        # in ANOTHER app). Poll NSPasteboard.changeCount as a fallback on darwin.
        self._mac_pasteboard_poll_timer: QTimer | None = None
        self._last_pasteboard_change_count: int = -1
        self.content_start_line: int = 3  #  configurable: which line to place content
        self.minimized: bool = False
        # Responsive UI: a single zoom factor scales fonts, paddings and fixed
        # widget sizes so the whole overlay shrinks to fit small screens.
        # Persisted across restarts. 1.0 = original INKIDEA dense size.
        self.ui_scale: float = 1.0
        self.UI_SCALE_MIN = 0.55
        self.UI_SCALE_MAX = 1.6
        self.UI_SCALE_STEP = 0.1
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
        # Mixed file+text: clipboard = text → user Cmd/Ctrl+V pastes text →
        # app sets clipboard = files → synthetic Cmd/Ctrl+V pastes files → advance chapter
        self._staged_pending_file_paths: list[str] | None = None
        self._suppress_paste_hotkey: bool = False
        self._staged_sequence_active: bool = False  # กัน Ctrl+V ซ้ำระหว่างรอ → advance ผิดรอบ
        # Safety net: if any step of the staged text→file→advance chain ever
        # raises or a timer never fires, _staged_sequence_active would stay True
        # and silently swallow every future paste. This watchdog force-clears it.
        self._staged_watchdog: QTimer | None = None
        # หลัง Ctrl+V ของคุณ (โหมดไฟล์+ข้อความ): แชทมักต้องรอก่อนค่อยรับ paste ข้อความ — ปรับได้ใน config.json
        self.staged_ms_after_user_paste = 450 if sys.platform == "darwin" else 350
        self.staged_ms_clipboard_to_ctrl_v = 450 if sys.platform == "darwin" else 90
        self.staged_ms_after_text_paste = 450 if sys.platform == "darwin" else 250
        self.staged_ms_simple_paste = 140 if sys.platform == "darwin" else 90

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

        # ---- apply saved UI zoom (scales the whole overlay to fit the screen)
        self._apply_scale(self.ui_scale)

        # position: centered on the primary screen
        screen = QApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        self.move(
            screen.x() + (screen.width() - self.width()) // 2,
            screen.y() + (screen.height() - self.height()) // 2,
        )

        self.show()
        # macOS: keep the overlay visible when Chrome (etc.) is focused — a
        # Qt::Tool panel otherwise hides on deactivate and the user "sees no
        # overlay" the moment they click into the target app. Re-apply shortly
        # after: Qt finishes realizing the NSWindow asynchronously and can reset
        # the level/behavior we set here.
        _macos_make_floating_overlay(self)
        QTimer.singleShot(600, lambda: _macos_make_floating_overlay(self))

        # ---- update check (background, non-blocking) -------------------------
        self._update_url = None
        self._update_tag = None
        self._update_artifact_url = None
        self._start_update_check()

        # ---- diagnostics tick (hotkey health + permission) --------------------
        self._start_diagnostics()

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
                    # Pick the artifact that matches this platform so the in-app
                    # updater can install without bouncing through a browser.
                    self._update_artifact_url = self._pick_release_artifact(data)
                    _log(f"Update available: {tag} (artifact={self._update_artifact_url or 'none'})")
                    self.signals.update_available.emit(tag, url)
            except Exception as exc:
                _log(f"Update check failed: {exc}", "WARN")

        threading.Thread(target=_run, daemon=True).start()

    def _pick_release_artifact(self, release_data: dict) -> str | None:
        """
        From a /releases/latest payload, return the best download URL for this OS:
          • Windows: prefer INKCOPY-Setup-*.exe (NSIS installer — auto-replaces in place).
                     Fallback to portable INKCOPY.exe.
          • macOS:   prefer INKCOPY-v*.dmg. Fallback to .zip.
        Returns None if no suitable artifact found.
        """
        assets = release_data.get("assets") or []
        if not isinstance(assets, list):
            return None

        def _match(predicate):
            for a in assets:
                name = (a.get("name") or "").lower()
                if predicate(name):
                    return a.get("browser_download_url")
            return None

        if sys.platform == "win32":
            return (
                _match(lambda n: n.startswith("inkcopy-setup") and n.endswith(".exe"))
                or _match(lambda n: n == "inkcopy.exe")
                or _match(lambda n: n.endswith(".exe"))
            )
        if sys.platform == "darwin":
            return (
                _match(lambda n: n.startswith("inkcopy") and n.endswith(".dmg"))
                or _match(lambda n: n.endswith(".dmg"))
                or _match(lambda n: n.endswith(".zip"))
            )
        return None

    def _on_update_available(self, tag: str, url: str):
        self._update_url = url
        self._update_tag = tag
        self.update_btn.setText(f"⬆ {tag}")
        self.update_btn.setToolTip(f"New version {tag} available — click to install")
        self.update_btn.setVisible(True)
        self.adjustSize()

    def _open_update(self):
        """
        Show a 3-option dialog: Install Now (silent download+install), Open Browser, Cancel.
        Install Now is only enabled when we matched a platform-specific artifact.
        """
        from PyQt6.QtWidgets import QMessageBox

        tag = getattr(self, "_update_tag", None) or "new version"
        artifact = getattr(self, "_update_artifact_url", None)

        msg = QMessageBox(self)
        msg.setWindowTitle(f"INKCOPY {tag} available")
        body = f"A new version of INKCOPY ({tag}) is available.\nCurrent version: {__version__}\n\n"
        if artifact:
            body += "Install now will download and run the installer."
        else:
            body += "No matching installer for this platform — opening the browser is your only option."
        msg.setText(body)
        msg.setIcon(QMessageBox.Icon.Information)

        install_btn = None
        if artifact:
            install_btn = msg.addButton("Install Now", QMessageBox.ButtonRole.AcceptRole)
        browser_btn = msg.addButton("Open Browser", QMessageBox.ButtonRole.ActionRole)
        cancel_btn = msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(install_btn or browser_btn)
        msg.exec()

        clicked = msg.clickedButton()
        if install_btn is not None and clicked is install_btn:
            self._install_update(artifact)
        elif clicked is browser_btn:
            if self._update_url:
                import webbrowser
                webbrowser.open(self._update_url)

    def _install_update(self, artifact_url: str):
        """
        Download artifact_url to a temp file with progress UI, then:
          • Windows: spawn `installer.exe /S` (silent) — NSIS kills running INKCOPY,
            replaces binary, relaunches via Finish-page action. We then quit.
          • macOS: open the .dmg in Finder so the user drags the new .app to
            /Applications (replacing a *running* bundle in place is unsafe — we
            don't attempt it). We then quit.
        Both flows log every step to LOG_PATH for postmortem.
        """
        from PyQt6.QtWidgets import QProgressDialog, QMessageBox
        import tempfile
        import urllib.request

        _log(f"Update install requested: {artifact_url}")

        suffix = ".exe" if sys.platform == "win32" else (".dmg" if sys.platform == "darwin" else ".bin")
        fd, tmp_path = tempfile.mkstemp(prefix="inkcopy-update-", suffix=suffix)
        os.close(fd)

        progress = QProgressDialog("Downloading update…", "Cancel", 0, 100, self)
        progress.setWindowTitle("INKCOPY Update")
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setValue(0)
        progress.show()
        QApplication.processEvents()

        try:
            req = urllib.request.Request(
                artifact_url,
                headers={"User-Agent": f"INKCOPY/{__version__}"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                downloaded = 0
                chunk = 64 * 1024
                with open(tmp_path, "wb") as out:
                    while True:
                        if progress.wasCanceled():
                            _log("Update download canceled by user")
                            progress.close()
                            try:
                                os.remove(tmp_path)
                            except OSError:
                                pass
                            return
                        buf = resp.read(chunk)
                        if not buf:
                            break
                        out.write(buf)
                        downloaded += len(buf)
                        if total:
                            progress.setValue(int(downloaded * 100 / total))
                        else:
                            progress.setLabelText(f"Downloading… {downloaded // 1024} KB")
                        QApplication.processEvents()
            progress.setValue(100)
            progress.close()
            _log(f"Update downloaded ({downloaded} bytes) → {tmp_path}")
        except Exception as exc:
            progress.close()
            _log(f"Update download FAILED: {exc}", "ERROR")
            QMessageBox.critical(self, "Update failed", f"Could not download update:\n{exc}")
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            return

        try:
            import subprocess
            if sys.platform == "win32":
                # /S = silent install (no UI). NSIS installer kills running INKCOPY,
                # replaces the .exe, and re-launches via MUI_FINISHPAGE_RUN.
                _log(f"Spawning Windows installer: {tmp_path} /S")
                subprocess.Popen([tmp_path, "/S"], close_fds=True, **_subprocess_no_window_kwargs())
            elif sys.platform == "darwin":
                _log(f"Opening DMG in Finder: {tmp_path}")
                subprocess.Popen(["open", tmp_path])
            else:
                _log(f"Linux update: revealing {tmp_path}")
                subprocess.Popen(["xdg-open", os.path.dirname(tmp_path)])
        except Exception as exc:
            _log(f"Launch installer FAILED: {exc}", "ERROR")
            QMessageBox.critical(self, "Update failed", f"Could not launch installer:\n{exc}")
            return

        # Quit ourselves so the installer can replace the binary (Windows) /
        # so the user can drag the new .app into place (Mac).
        QTimer.singleShot(500, self._quit)

    # ==================================================================== UI
    def _build_ui(self):
        root = QVBoxLayout()
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(8)
        self._root_layout = root  # kept so _apply_scale can rescale margins

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

        # -- UI zoom controls (responsive scaling for small screens)
        self.zoom_out_btn = QPushButton("−")
        self.zoom_out_btn.setObjectName("zoomBtn")
        self.zoom_out_btn.setFixedSize(22, 22)
        self.zoom_out_btn.setToolTip("ย่อขนาด UI ทั้งหมด (Ctrl + ล้อเมาส์ลง)")
        self.zoom_out_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.zoom_out_btn.clicked.connect(lambda: self._nudge_ui_scale(-self.UI_SCALE_STEP))
        self.zoom_label = QPushButton("100%")
        self.zoom_label.setObjectName("zoomLabel")
        self.zoom_label.setToolTip("ขนาด UI ปัจจุบัน — คลิกเพื่อรีเซ็ตเป็น 100%")
        self.zoom_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.zoom_label.setFlat(True)
        self.zoom_label.clicked.connect(lambda: self._set_ui_scale(1.0, save=True))
        self.zoom_in_btn = QPushButton("+")
        self.zoom_in_btn.setObjectName("zoomBtn")
        self.zoom_in_btn.setFixedSize(22, 22)
        self.zoom_in_btn.setToolTip("ขยายขนาด UI ทั้งหมด (Ctrl + ล้อเมาส์ขึ้น)")
        self.zoom_in_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.zoom_in_btn.clicked.connect(lambda: self._nudge_ui_scale(self.UI_SCALE_STEP))

        title_row.addWidget(self.title_label)
        title_row.addWidget(self.update_btn)
        title_row.addStretch()
        title_row.addWidget(self.zoom_out_btn)
        title_row.addWidget(self.zoom_label)
        title_row.addWidget(self.zoom_in_btn)
        title_row.addSpacing(8)
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

        # -- diagnostics row (hotkey health + permission + open log)
        diag_row = QHBoxLayout()
        self.diag_label = QLabel("Hotkey: …")
        self.diag_label.setObjectName("diagLabel")
        self.diag_label.setWordWrap(True)
        self.open_log_btn = QPushButton("🔍 Open Log")
        self.open_log_btn.setObjectName("controlBtn")
        self.open_log_btn.setToolTip(f"Open log folder ({LOG_PATH})")
        self.open_log_btn.clicked.connect(self._open_log_folder)
        diag_row.addWidget(self.diag_label, 1)
        diag_row.addWidget(self.open_log_btn)
        self._row_diag = QWidget()
        self._row_diag.setLayout(diag_row)
        root.addWidget(self._row_diag)

        # -- compact controls shown ONLY while minimized, so prev / pause / next
        #    / reset stay usable without expanding the overlay. The full controls
        #    live inside content_widget (hidden when minimized), so these mirror
        #    them and call the same handlers.
        self.mini_prev_btn = QPushButton("◀ Prev")
        self.mini_prev_btn.setObjectName("controlBtn")
        self.mini_prev_btn.clicked.connect(self._go_prev)
        self.mini_pause_btn = QPushButton("⏸ Pause")
        self.mini_pause_btn.setObjectName("controlBtn")
        self.mini_pause_btn.clicked.connect(self._toggle_pause)
        self.mini_next_btn = QPushButton("Next ▶")
        self.mini_next_btn.setObjectName("controlBtn")
        self.mini_next_btn.clicked.connect(self._go_next)
        self.mini_reset_btn = QPushButton("↺")
        self.mini_reset_btn.setObjectName("controlBtn")
        self.mini_reset_btn.setToolTip("Reset to first chapter")
        self.mini_reset_btn.clicked.connect(self._reset_index)
        mini_row = QHBoxLayout()
        mini_row.setContentsMargins(0, 0, 0, 0)
        mini_row.addWidget(self.mini_prev_btn)
        mini_row.addWidget(self.mini_pause_btn)
        mini_row.addWidget(self.mini_next_btn)
        mini_row.addWidget(self.mini_reset_btn)
        self._mini_controls = QWidget()
        self._mini_controls.setLayout(mini_row)
        self._mini_controls.hide()  # only visible while minimized
        root.addWidget(self._mini_controls)

        # Container for collapsible content
        self.content_widget = QWidget()
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)
        self._content_layout = content_layout  # kept so _apply_scale can rescale

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

    # ============================================================ SCALING
    def _px(self, v: float) -> int:
        """Scale a base pixel value by the current UI zoom (min 1px)."""
        return max(1, round(v * self.ui_scale))

    # ============================================================ STYLING
    def _apply_styles(self):
        s = self._px  # every px below is scaled by self.ui_scale
        self.setStyleSheet(f"""
            QWidget {{
                font-family: 'Segoe UI', 'Noto Sans Thai', sans-serif;
                font-size: {s(13)}px;
                color: #e0e0e0;
            }}
            #title {{
                font-size: {s(16)}px;
                font-weight: bold;
                color: #ffffff;
            }}
            #status {{
                font-size: {s(14)}px;
                padding: {s(6)}px {s(10)}px;
                background: rgba(255,255,255,0.07);
                border-radius: {s(8)}px;
                color: #90ee90;
            }}
            #modeBtn {{
                background: rgba(80,180,255,0.18);
                border: 1px solid rgba(80,180,255,0.35);
                border-radius: {s(8)}px;
                padding: {s(8)}px {s(14)}px;
                color: #80d4ff;
                font-size: {s(13)}px;
                font-weight: bold;
            }}
            #modeBtn:hover {{
                background: rgba(80,180,255,0.30);
            }}
            #actionBtn {{
                background: rgba(255,255,255,0.12);
                border: 1px solid rgba(255,255,255,0.18);
                border-radius: {s(8)}px;
                padding: {s(6)}px {s(14)}px;
                color: #ffffff;
            }}
            #actionBtn:hover {{
                background: rgba(255,255,255,0.22);
            }}
            #controlBtn {{
                background: rgba(255,255,255,0.10);
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: {s(6)}px;
                padding: {s(6)}px {s(12)}px;
                color: #e0e0e0;
                font-size: {s(12)}px;
            }}
            #controlBtn:hover {{
                background: rgba(255,255,255,0.20);
            }}
            #info {{
                color: #aaaaaa;
                font-size: {s(12)}px;
            }}
            #diagLabel {{
                color: #cccccc;
                font-size: {s(11)}px;
                padding: {s(4)}px {s(8)}px;
                background: rgba(255,255,255,0.04);
                border-radius: {s(6)}px;
                border: 1px solid rgba(255,255,255,0.08);
            }}
            #legend {{
                font-size: {s(11)}px;
                color: #888888;
                margin-top: {s(4)}px;
            }}
            QScrollArea#promptListScroll,
            QWidget#promptListViewport,
            QWidget#promptFilesInner {{
                background: transparent;
                border: none;
            }}
            #closeBtn {{
                background: transparent;
                border: none;
                color: #888888;
                font-size: {s(16)}px;
            }}
            #closeBtn:hover {{
                color: #ff5555;
            }}
            #minimizeBtn {{
                background: transparent;
                border: none;
                color: #888888;
                font-size: {s(18)}px;
                font-weight: bold;
            }}
            #minimizeBtn:hover {{
                color: #ffffff;
            }}
            #zoomBtn {{
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: {s(5)}px;
                color: #cfcfcf;
                font-size: {s(14)}px;
                font-weight: bold;
                padding: 0;
            }}
            #zoomBtn:hover {{
                background: rgba(255,255,255,0.20);
                color: #ffffff;
            }}
            #zoomLabel {{
                color: #aaaaaa;
                font-size: {s(11)}px;
                min-width: {s(34)}px;
            }}
            #updateBtn {{
                background: #2d5a2d;
                color: #aaffaa;
                border: 1px solid #3d7a3d;
                border-radius: {s(8)}px;
                padding: {s(1)}px {s(8)}px;
                margin-left: {s(8)}px;
                font-size: {s(11)}px;
                font-weight: bold;
            }}
            #updateBtn:hover {{
                background: #3d7a3d;
                color: #ffffff;
            }}
            QCheckBox {{
                spacing: {s(8)}px;
                color: #e0e0e0;
                padding: {s(2)}px;
            }}
            QCheckBox::indicator {{
                width: {s(16)}px;
                height: {s(16)}px;
                border: 1px solid #6a7a8a;
                border-radius: {s(3)}px;
                background: rgba(255,255,255,0.05);
            }}
            QCheckBox::indicator:hover {{
                border-color: #4a9eff;
                background: rgba(74,158,255,0.10);
            }}
            QCheckBox::indicator:checked {{
                background: #2680eb;
                border: 1px solid #4a9eff;
                image: none;
            }}
            QCheckBox::indicator:checked:hover {{
                background: #3a8df0;
            }}
            QRadioButton {{
                spacing: {s(8)}px;
                color: #e0e0e0;
                padding: {s(2)}px;
            }}
            QRadioButton::indicator {{
                width: {s(16)}px;
                height: {s(16)}px;
                border: 1px solid #6a7a8a;
                border-radius: {s(8)}px;
                background: rgba(255,255,255,0.05);
            }}
            QRadioButton::indicator:hover {{
                border-color: #4a9eff;
                background: rgba(74,158,255,0.10);
            }}
            QRadioButton::indicator:checked {{
                background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
                    stop:0 #ffffff, stop:0.40 #ffffff, stop:0.45 #2680eb, stop:1 #2680eb);
                border: 1px solid #4a9eff;
            }}
            QRadioButton::indicator:checked:hover {{
                border-color: #6ab2ff;
            }}
            #numberInput {{
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.20);
                border-radius: {s(6)}px;
                padding: {s(4)}px {s(8)}px;
                color: #ffffff;
                font-size: {s(12)}px;
                selection-background-color: #2680eb;
            }}
            #numberInput:focus {{
                border: 1px solid #4a9eff;
                background: rgba(74,158,255,0.10);
            }}
            #addBtn {{
                background: rgba(80,200,120,0.18);
                border: 1px solid rgba(80,200,120,0.45);
                border-radius: {s(6)}px;
                padding: {s(6)}px {s(12)}px;
                color: #8eecb0;
                font-size: {s(12)}px;
                font-weight: bold;
            }}
            #addBtn:hover {{
                background: rgba(80,200,120,0.32);
                color: #ffffff;
            }}
            #rowRemoveBtn {{
                background: rgba(255,80,80,0.10);
                border: 1px solid rgba(255,80,80,0.30);
                border-radius: {s(4)}px;
                color: #ff8a8a;
                font-size: {s(11)}px;
                font-weight: bold;
                padding: 0;
            }}
            #rowRemoveBtn:hover {{
                background: rgba(255,80,80,0.30);
                color: #ffffff;
                border-color: #ff5555;
            }}
        """)

    def _apply_scale(self, scale: float, *, save: bool = False):
        """Apply a UI zoom factor: rescale fonts/paddings (via stylesheet) plus
        every fixed widget size and layout margin, then resize the window to fit.
        This is the 'scale the whole UI' behaviour (not a scroll area)."""
        scale = max(self.UI_SCALE_MIN, min(self.UI_SCALE_MAX, round(scale, 3)))
        self.ui_scale = scale
        s = self._px

        # Stylesheet (fonts, paddings, indicator sizes) — scaled.
        self._apply_styles()
        # Re-apply the mode button's accent style (Copy/Vocab) at the new scale.
        self._apply_mode_btn_style()

        # Fixed widget sizes.
        for btn in (self.minimize_btn, self.close_btn):
            btn.setFixedSize(s(24), s(24))
        for btn in (self.zoom_out_btn, self.zoom_in_btn):
            btn.setFixedSize(s(22), s(22))
        self.range_from.setFixedWidth(s(70))
        self.range_to.setFixedWidth(s(70))
        self.jump_input.setFixedWidth(s(80))
        self.vocab_filename_input.setFixedWidth(s(200))
        for btn in (self.concurrent_minus_btn, self.concurrent_plus_btn,
                    self.line_minus_btn, self.line_plus_btn):
            btn.setFixedWidth(s(32))
        small_label_css = f"font-weight: bold; min-width: {s(20)}px;"
        self.concurrent_value_label.setStyleSheet(small_label_css)
        self.line_value_label.setStyleSheet(small_label_css)

        # Layout margins / spacing.
        self._root_layout.setContentsMargins(s(18), s(14), s(18), s(14))
        self._root_layout.setSpacing(s(8))
        self._content_layout.setSpacing(s(8))
        if hasattr(self, "prompt_rows_layout"):
            self.prompt_rows_layout.setContentsMargins(s(6), s(6), s(6), s(6))
            self.prompt_rows_layout.setSpacing(s(6))

        # Window minimum width scales too so it can actually get small.
        self.setMinimumWidth(s(520))

        # Per-row remove buttons live in the scroll area — rescale + re-measure.
        self._rescale_prompt_rows()
        self._resize_prompt_scroll_area()

        if hasattr(self, "zoom_label"):
            self.zoom_label.setText(f"{round(self.ui_scale * 100)}%")

        self.adjustSize()
        if save:
            self._save_config()

    def _rescale_prompt_rows(self):
        """Resize the ✕ remove buttons inside the prompt list to the new scale."""
        if not hasattr(self, "prompt_rows_layout"):
            return
        size = self._px(22)
        for i in range(self.prompt_rows_layout.count()):
            item = self.prompt_rows_layout.itemAt(i)
            w = item.widget() if item else None
            if w is None:
                continue
            for btn in w.findChildren(QPushButton):
                if btn.objectName() == "rowRemoveBtn":
                    btn.setFixedSize(size, size)

    def _apply_mode_btn_style(self):
        """Accent style for the mode button per current mode. Only colours are
        set here — paddings/radius/font come from the scaled #modeBtn rule."""
        if self.mode == self.MODE_COPY:
            self.mode_btn.setStyleSheet(
                "#modeBtn { background: rgba(255,160,50,0.20); "
                "border: 1px solid rgba(255,160,50,0.40); color: #ffb347; }"
                "#modeBtn:hover { background: rgba(255,160,50,0.35); }"
            )
        elif self.mode == self.MODE_VOCAB:
            self.mode_btn.setStyleSheet(
                "#modeBtn { background: rgba(180,100,255,0.20); "
                "border: 1px solid rgba(180,100,255,0.40); color: #c896ff; }"
                "#modeBtn:hover { background: rgba(180,100,255,0.35); }"
            )
        else:
            self.mode_btn.setStyleSheet("")

    def _nudge_ui_scale(self, delta: float):
        self._set_ui_scale(self.ui_scale + delta, save=True)

    def _set_ui_scale(self, scale: float, *, save: bool = False):
        self._apply_scale(scale, save=save)

    def wheelEvent(self, event):
        # Ctrl + mouse wheel = zoom the whole UI (matches editors/browsers).
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            dy = event.angleDelta().y()
            if dy:
                self._nudge_ui_scale(self.UI_SCALE_STEP if dy > 0 else -self.UI_SCALE_STEP)
                event.accept()
                return
        super().wheelEvent(event)

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
            # A staged round is mid-flight (we're swapping clipboard text→file
            # and synth-pasting). Drop any real Ctrl+V that arrives now: honoring
            # it would either double-advance after the sequence ends or restart
            # the timer mid-swap. The user's next *real* paste lands after the
            # sequence clears _staged_sequence_active.
            if self._staged_sequence_active:
                return True
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
        mac = sys.platform == "darwin"
        default_after_user = 450 if mac else 350
        default_clipboard_to_paste = 450 if mac else 90
        default_after_text = 450 if mac else 250
        default_simple = 140 if mac else 90
        min_clipboard_to_paste = 250 if mac else 30
        min_after_text = 250 if mac else 50
        self.staged_ms_after_user_paste = max(50, min(int(cfg.get("staged_ms_after_user_paste", default_after_user)), 8000))
        self.staged_ms_clipboard_to_ctrl_v = max(
            min_clipboard_to_paste,
            min(int(cfg.get("staged_ms_clipboard_to_ctrl_v", default_clipboard_to_paste)), 3000),
        )
        self.staged_ms_after_text_paste = max(min_after_text, min(int(cfg.get("staged_ms_after_text_paste", default_after_text)), 8000))
        self.staged_ms_simple_paste = max(40, min(int(cfg.get("staged_ms_simple_paste", default_simple)), 3000))
        try:
            self.ui_scale = max(self.UI_SCALE_MIN, min(self.UI_SCALE_MAX, float(cfg.get("ui_scale", 1.0))))
        except (TypeError, ValueError):
            self.ui_scale = 1.0
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
            "ui_scale": round(self.ui_scale, 3),
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
            remove_btn.setFixedSize(self._px(22), self._px(22))
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
        layout_margins = self._px(6) * 2  # top + bottom from setContentsMargins
        row_spacing = self._px(6)         # from setSpacing
        rows_to_show = min(n, self.PROMPT_ROWS_BEFORE_SCROLL)
        # Measure the actual heights of the first rows_to_show rows.
        row_heights: list[int] = []
        for i in range(rows_to_show):
            item = self.prompt_rows_layout.itemAt(i)
            w = item.widget() if item else None
            if w is not None:
                row_heights.append(max(w.sizeHint().height(), self._px(28)))
        if not row_heights:
            self.prompt_list_scroll.setFixedHeight(0)
            return
        total = sum(row_heights) + row_spacing * (len(row_heights) - 1) + layout_margins
        self.prompt_list_scroll.setFixedHeight(total + self._px(4))  # fudge for borders

    @staticmethod
    def _read_local_file_as_text(path: str, label: str) -> str:
        try:
            # utf-8-sig handles both BOM-prefixed (Windows Notepad) and plain
            # UTF-8 files transparently — Thai text stays intact either way.
            with open(path, "r", encoding="utf-8-sig") as f:
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
            self._apply_mode_btn_style()
            self._start_clipboard_monitor()
        elif self.mode == self.MODE_COPY:
            self.mode = self.MODE_VOCAB
            self.mode_btn.setText(f"📖 [VOCAB MODE]  Clipboard → {self.vocab_filename} (append)")
            self._apply_mode_btn_style()
            self._init_vocab_mode()
        else:
            self.mode = self.MODE_PASTE
            self.mode_btn.setText("📋 [PASTE MODE]  Prompt+Chapter → Clipboard")
            self._apply_mode_btn_style()
            self._stop_clipboard_monitor()
        self.paused = False
        self._set_pause_text("⏸ Pause")
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
            # utf-8-sig transparently strips BOM if present (from prior writes).
            with open(self.vocab_file_path, "r", encoding="utf-8-sig") as f:
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

        # macOS: ask the OS to show its Accessibility grant dialog on first
        # registration so hotkeys don't silently no-op when permission is missing.
        if sys.platform == "darwin":
            _macos_prompt_accessibility()

        _hotkey_backend.register(
            on_paste=self._kb_paste_handler,
            on_prev=lambda: self.signals.prev_chapter.emit(),
            on_next=lambda: self.signals.next_chapter.emit(),
            on_pause=lambda: self.signals.toggle_pause.emit(),
        )

    def _kb_paste_handler(self):
        # Backend already verified the paste modifier (Ctrl on Win/Linux, Cmd on macOS).
        if self._suppress_paste_hotkey:
            return
        if self.mode == self.MODE_PASTE and not self.paused:
            # ส่ง event เข้า Qt main thread จาก hotkey listener thread
            QApplication.postEvent(self, QEvent(self._get_paste_hotkey_event_type()))

    # ============================================================ CLIPBOARD MONITOR (Copy Mode)
    def _start_clipboard_monitor(self):
        clipboard = QApplication.clipboard()
        self._last_clipboard_text = clipboard.text() or ""
        clipboard.dataChanged.connect(self._clipboard_data_changed)
        # macOS fallback: poll the pasteboard changeCount so copies made in
        # another app (while INKCOPY is a background overlay) are still caught.
        if sys.platform == "darwin":
            self._last_pasteboard_change_count = self._read_pasteboard_change_count()
            if self._mac_pasteboard_poll_timer is None:
                self._mac_pasteboard_poll_timer = QTimer(self)
                self._mac_pasteboard_poll_timer.setInterval(300)  # ms
                self._mac_pasteboard_poll_timer.timeout.connect(self._poll_mac_pasteboard)
            self._mac_pasteboard_poll_timer.start()

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
        if self._mac_pasteboard_poll_timer is not None:
            self._mac_pasteboard_poll_timer.stop()

    def _read_pasteboard_change_count(self) -> int:
        """macOS NSPasteboard.changeCount(), or -1 if unavailable."""
        try:
            from AppKit import NSPasteboard
            return int(NSPasteboard.generalPasteboard().changeCount())
        except Exception:
            return -1

    def _poll_mac_pasteboard(self):
        """macOS COPY/VOCAB fallback: detect a pasteboard change and route it
        through the same handler so all mode/paused/ignore guards still apply."""
        if sys.platform != "darwin":
            return
        cc = self._read_pasteboard_change_count()
        if cc < 0 or cc == self._last_pasteboard_change_count:
            return
        self._last_pasteboard_change_count = cc
        self._clipboard_data_changed()

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
        # utf-8-sig writes a BOM so macOS TextEdit / Pages don't misdetect
        # Thai text as MacRoman / Western when opening the .txt later.
        with open(out_path, "w", encoding="utf-8-sig") as f:
            f.write(content)
        _log(f"Copy mode saved: {out_path} ({len(content)} chars, utf-8-sig)")

        end_slot = self.current_index + chapters_in_round
        ch_label = self._ch_range_label(self.current_index, end_slot - 1)
        if chapters_in_round == 1:
            prog = f"{ch_label}  ({self.current_index + 1}/{total})"
        else:
            prog = f"{ch_label}  ({self.current_index + 1}-{end_slot}/{total})"
        self._show_toast(f"💾 SAVED: {prog}", "copy")

        self.status_label.setText(f"[SAVED] {prog}")
        # Colour-only override: padding/radius/font come from the scaled #status rule.
        self.status_label.setStyleSheet("#status { color: #80ff80; }")

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

        # Append to vocab.txt — write BOM only when creating an empty/new file
        # so macOS apps detect UTF-8 instead of falling back to MacRoman.
        file_has_content = (
            os.path.isfile(self.vocab_file_path)
            and os.path.getsize(self.vocab_file_path) > 0
        )
        encoding = "utf-8" if file_has_content else "utf-8-sig"
        with open(self.vocab_file_path, "a", encoding=encoding) as f:
            if self.vocab_entry_count > 0:
                # Add blank line separator before new entry
                f.write("\n\n")
            f.write(text.strip())
        _log(
            f"Vocab appended: entry #{self.vocab_entry_count + 1} "
            f"({len(text.strip())} chars, encoding={encoding})"
        )
        
        self.vocab_entry_count += 1
        
        self._show_toast(f"📝 VOCAB SAVED: Entry #{self.vocab_entry_count}", "vocab")
        
        self.status_label.setText(
            f"[SAVED] Vocab entry #{self.vocab_entry_count}"
        )
        self.status_label.setStyleSheet("#status { color: #c896ff; }")

        QTimer.singleShot(1500, self._update_status)

    # ============================================================ PASTE MODE CLIPBOARD
    def _load_clipboard_paste_mode(self):
        if not self.chapter_files:
            return

        self._staged_pending_file_paths = None
        self._staged_sequence_active = False
        self._staged_stop_watchdog()
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
        file_paths = [p for k, p in ordered_parts if k == "file"]
        text_combined = "\n\n".join(p for k, p in ordered_parts if k == "text")

        # แอปเว็บมักรับแค่ไฟล์ถ้ามีทั้ง URL และ text ในคลิปบอร์ดชุดเดียว — แยกหลายรอบ:
        # Mixed paste: user Cmd+V → text pasted | synthetic Cmd+V → files pasted | advance
        if has_text and has_file:
            wrote_native_text = _set_clipboard_text_native(text_combined)
            if not wrote_native_text:
                mime.setText(text_combined)
                clipboard.setMimeData(mime)
            self._staged_pending_file_paths = file_paths
            _log(
                f"Paste mode (mixed): text={len(text_combined)} chars, "
                f"files={len(file_paths)} staged, native_text={wrote_native_text}"
            )
        elif has_text:
            wrote_native_text = _set_clipboard_text_native(text_combined)
            if not wrote_native_text:
                mime.setText(text_combined)
                clipboard.setMimeData(mime)
            _log(f"Paste mode (text-only): {len(text_combined)} chars, native_text={wrote_native_text}")
        elif has_file:
            # Native write keeps clipboard ownership consistent with the text
            # write (macOS NSPasteboard / Windows CF_HDROP); browsers ignore
            # Qt's legacy file URL format on some macOS versions anyway. Fall
            # back to Qt only if the native write fails (e.g. Linux).
            wrote_native = _set_clipboard_files_native(file_paths)
            if not wrote_native:
                mime.setUrls([QUrl.fromLocalFile(p) for p in file_paths])
                clipboard.setMimeData(mime)
            _log(f"Paste mode (file-only): {len(file_paths)} files, native={wrote_native}")
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
            self._staged_begin_watchdog()
            try:
                self._run_staged_file_paste_then_finish(paths)
            except Exception as exc:
                _log(f"Staged paste sequence crashed: {exc}", "ERROR")
                self._staged_reset_state()
            return

        self._finish_paste_advance()

    def _staged_begin_watchdog(self):
        """Arm a one-shot timer that force-clears a stuck staged sequence.
        Reuses a single timer so repeated pastes don't leak QTimer objects."""
        if self._staged_watchdog is None:
            self._staged_watchdog = QTimer(self)
            self._staged_watchdog.setSingleShot(True)
            self._staged_watchdog.timeout.connect(self._staged_watchdog_fire)
        self._staged_watchdog.start(8000)

    def _staged_stop_watchdog(self):
        if self._staged_watchdog is not None:
            self._staged_watchdog.stop()

    def _staged_watchdog_fire(self):
        if self._staged_sequence_active:
            _log("Staged sequence watchdog fired — force-clearing stuck state", "WARN")
            self._staged_reset_state()
            self._update_status()

    def _staged_reset_state(self):
        self._suppress_paste_hotkey = False
        self._ignore_clipboard_change = False
        self._staged_sequence_active = False
        self._staged_stop_watchdog()

    def _run_staged_file_paste_then_finish(self, paths: list[str]):
        """หลังคุณ Ctrl+V วางข้อความแล้ว — ตั้งคลิปบอร์ดเป็นไฟล์แล้ว Ctrl+V สังเคราะห์."""
        self._ignore_clipboard_change = True
        # Native CF_HDROP (Win) / NSPasteboard (mac) keeps ownership consistent
        # with the text write so the rapid text→file→text swaps don't leave a
        # half-written clipboard. Fall back to Qt only if the native write fails.
        wrote_native = _set_clipboard_files_native(paths)
        if not wrote_native:
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
            QApplication.clipboard().setMimeData(mime)
        QApplication.processEvents()
        _log(f"Staged file paste: {len(paths)} files queued (native={wrote_native})")
        min_ms = 250 if sys.platform == "darwin" else 40
        ms = max(min_ms, min(self.staged_ms_clipboard_to_ctrl_v, 3000))
        # After the synthetic file paste, advance to the next chapter directly.
        # The previous 0.2.1 flow re-pasted the text a third time "for chat
        # ordering" but observation shows Gemini/ChatGPT already place files
        # under the message body regardless of paste order — the third paste
        # only adds a race window where chapter advance can be missed.
        QTimer.singleShot(ms, lambda: self._staged_send_synthetic_ctrl_v(None))

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
        """ส่ง Ctrl+V (หรือ Cmd+V บน macOS) สังเคราะห์; หลังดีเลย์เรียก after_delay หรือจบรอบ."""
        self._suppress_paste_hotkey = True
        sent = False
        if sys.platform == "win32":
            if not _win32_sendinput_ctrl_v():
                try:
                    self._inject_ctrl_v_windows()
                    sent = True
                except Exception:
                    pass
                sent = _hotkey_backend.send_paste() or sent
            else:
                sent = True
        else:
            sent = _hotkey_backend.send_paste()
        if not sent:
            _log("Synthetic paste failed; leaving staged files on clipboard for manual paste", "ERROR")
            QTimer.singleShot(50, self._staged_clear_suppress_without_advance)
            return
        min_ms = 250 if sys.platform == "darwin" else 50
        ms = max(min_ms, min(self.staged_ms_after_text_paste, 8000))
        done = after_delay if after_delay is not None else self._staged_clear_suppress_and_advance
        QTimer.singleShot(ms, done)

    def _staged_clear_suppress_without_advance(self):
        self._staged_reset_state()
        self.status_label.setText(f"[READY] Files are on clipboard — press {PASTE_MODIFIER_NAME}+V once")

    def _staged_clear_suppress_and_advance(self):
        self._staged_reset_state()
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
        self._set_pause_text("⏸ Pause")
        if self.mode == self.MODE_PASTE:
            self._load_clipboard_paste_mode()
        else:
            self._update_status()

    def _toggle_pause(self):
        self.paused = not self.paused
        if self.paused:
            self._set_pause_text("▶ Resume")
            self.status_label.setText("[PAUSED]  Press F12 or Resume to continue")
            self.status_label.setStyleSheet("#status { color: #ffcc00; }")
        else:
            self._set_pause_text("⏸ Pause")
            self.status_label.setStyleSheet("")
            if self.mode == self.MODE_PASTE:
                self._load_clipboard_paste_mode()
            else:
                self._update_status()

    # ============================================================ MINIMIZE/EXPAND
    def _toggle_minimize(self):
        self.minimized = not self.minimized
        if self.minimized:
            # Minimized = compact HUD: keep mode + chapter status + title buttons
            # + prev/pause/next; hide the content and the diagnostics/log row
            # (accessibility status + Open Log) so it stays clean.
            self.content_widget.hide()
            self._row_diag.hide()
            self._mini_controls.show()
            self.minimize_btn.setText("□")
            self.adjustSize()
        else:
            self.content_widget.show()
            self._row_diag.show()
            self._mini_controls.hide()
            self.minimize_btn.setText("−")
            self.adjustSize()

    def _set_pause_text(self, text: str):
        """Keep the full and minimized pause buttons in sync."""
        self.pause_btn.setText(text)
        if hasattr(self, "mini_pause_btn"):
            self.mini_pause_btn.setText(text)

    # ============================================================ TOAST NOTIFICATION
    def _show_toast(self, message: str, action_type: str):
        if self.toast:
            self.toast.close()
        self.toast = ToastNotification(message, action_type)
        self.toast.show()
        # Same macOS fix: the toast must show over the focused app (Chrome),
        # otherwise the "PASTED/SAVED" confirmation never appears on macOS.
        _macos_make_floating_overlay(self.toast)

    # ============================================================ DIAGNOSTICS
    def _start_diagnostics(self):
        """Tick every 2s — refresh hotkey health label + auto-restart listener if dead."""
        self._diag_timer = QTimer(self)
        self._diag_timer.timeout.connect(self._diagnostics_tick)
        self._diag_timer.start(2000)
        self._diagnostics_tick()  # immediate first refresh

    def _diagnostics_tick(self):
        stats = getattr(_hotkey_backend, "stats", {}) or {}
        alive = False
        try:
            alive = bool(_hotkey_backend.is_alive())
        except Exception:
            alive = False

        registered = self.hotkeys_registered
        bits: list[str] = []

        if sys.platform == "darwin":
            # DMG path is the #1 silent cause of "permission ON but no events"
            # — surface it loudly before showing the toggle statuses.
            if _running_from_macos_dmg():
                bits.append(
                    "🔴 Running from DMG (/Volumes/) — macOS will refuse to remember "
                    "permissions. Drag INKCOPY.app to /Applications/ and re-grant."
                )

            ax_trusted = _macos_accessibility_trusted()  # True / False / None
            if ax_trusted is False:
                bits.append("🔴 Accessibility: NOT trusted (System Settings → Privacy & Security → Accessibility — remove & re-add INKCOPY)")
            elif ax_trusted is True:
                bits.append("🟢 Accessibility: trusted")
            else:
                bits.append("🟡 Accessibility: unknown")

            im_trusted = _macos_input_monitoring_trusted()
            if im_trusted is False:
                bits.append("🔴 Input Monitoring: NOT granted (System Settings → Privacy & Security → Input Monitoring — add INKCOPY)")
            elif im_trusted is True:
                bits.append("🟢 Input Monitoring: granted")
            else:
                bits.append("🟡 Input Monitoring: unknown")

            # Auto-recover: if the user grants Accessibility / Input Monitoring
            # while INKCOPY is already running, the listener (started without
            # permission) keeps receiving ZERO events — so a Cmd+V pastes into
            # the target app but is never detected and the chapter never
            # advances. Detect the False→True permission edge and restart the
            # listener so paste-advance starts working WITHOUT a Quit & reopen.
            if registered:
                prev_ax = getattr(self, "_ax_last", None)
                prev_im = getattr(self, "_im_last", None)
                if (ax_trusted is True and prev_ax is False) or (
                    im_trusted is True and prev_im is False
                ):
                    _log("macOS permission granted at runtime — restarting hotkey listener")
                    self._restart_hotkeys()
                self._ax_last = ax_trusted
                self._im_last = im_trusted

        if not registered:
            bits.append("⚪ Hotkeys not registered yet — set Prompt + Chapter folder first")
        elif alive:
            tap = " tap=on" if stats.get("event_tap_started") else ""
            bits.append(
                f"🟢 Hotkey listener: alive{tap} · keys={stats.get('keys_received', 0)} "
                f"V={stats.get('v_keys_seen', 0)} pastes={stats.get('paste_fires', 0)} "
                f"F9={stats.get('prev_fires', 0)} F10={stats.get('next_fires', 0)}"
            )
            # If the listener is alive but has received ZERO keys after we've been
            # waiting more than a few seconds, the most likely cause on macOS is
            # the permission split. Add an explicit hint so users don't have to
            # guess what to do next.
            if sys.platform == "darwin" and registered and stats.get("keys_received", 0) == 0:
                bits.append("⚠ No keys observed — check Input Monitoring permission, then Quit & reopen INKCOPY")
        else:
            bits.append("🔴 Hotkey listener: DEAD — attempting restart")
            _log("Listener dead — attempting restart", "WARN")
            self._restart_hotkeys()

        last_err = stats.get("last_error") or ""
        if last_err:
            bits.append(f"⚠ last error: {last_err}")

        self.diag_label.setText("  ·  ".join(bits))

    def _restart_hotkeys(self):
        try:
            _hotkey_backend.unregister()
        except Exception:
            pass
        self.hotkeys_registered = False
        try:
            self._register_hotkeys()
            _log("Listener restart attempt completed")
        except Exception as exc:
            _log(f"Listener restart FAILED: {exc}", "ERROR")

    def _open_log_folder(self):
        try:
            os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        except OSError:
            pass
        # Make sure the log file exists so the OS reveal-in-folder doesn't fail.
        if not os.path.isfile(LOG_PATH):
            try:
                with open(LOG_PATH, "a", encoding="utf-8"):
                    pass
            except OSError:
                pass
        try:
            import subprocess
            if sys.platform == "darwin":
                subprocess.Popen(["open", "-R", LOG_PATH])
            elif sys.platform == "win32":
                subprocess.Popen(["explorer", "/select,", LOG_PATH])
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(LOG_PATH)])
        except Exception as exc:
            _log(f"open log folder failed: {exc}", "ERROR")

    # ============================================================ QUIT
    def _quit(self):
        _hotkey_backend.unregister()
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
