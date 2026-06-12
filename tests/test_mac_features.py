"""Functional tests for INKCOPY's core features on macOS.

Goal: paste, copy, next, prev, and the "true auto-switch clipboard" staged
sequence must behave correctly — in particular each hotkey press must advance
exactly ONE round (the macOS double-fire bug made them advance twice).
"""
from __future__ import annotations

import os
import sys

import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

from conftest import configure_copy, configure_paste

IS_MAC = sys.platform == "darwin"


def pb_types():
    """Live macOS system-pasteboard UTI list (what the target app would see)."""
    from AppKit import NSPasteboard

    pb = NSPasteboard.generalPasteboard()
    return [str(t) for t in (pb.types() or [])]


def pb_has_file_url():
    return any(("file-url" in t) or ("Filenames" in t) for t in pb_types())


def clip_text():
    """What the *target* app would paste.

    On macOS the app writes via the native NSPasteboard (so browsers see real
    file URLs / text), bypassing Qt's clipboard — so read the system pasteboard
    there. Elsewhere Qt's clipboard is the source of truth.
    """
    if IS_MAC:
        from AppKit import NSPasteboard, NSPasteboardTypeString

        pb = NSPasteboard.generalPasteboard()
        return str(pb.stringForType_(NSPasteboardTypeString) or "")
    return QApplication.clipboard().text()


# --------------------------------------------------------------------------- #
# PASTE mode — text only
# --------------------------------------------------------------------------- #
def test_paste_text_only_loads_combined_text(ik):
    configure_paste(ik, prompt_as_text=True, chapter_as_text=True, concurrent=1)
    ik._load_clipboard_paste_mode()
    text = clip_text()
    assert "professional Thai-to-English" in text   # system prompt
    assert "Glossary" in text                        # glossary prompt
    assert "chapter 1" in text                       # first chapter body
    assert ik._staged_pending_file_paths is None     # no files staged


def test_paste_text_only_advances_exactly_one_round(ik):
    """One paste = +1 round. Regression for the macOS double-advance bug."""
    configure_paste(ik, prompt_as_text=True, chapter_as_text=True, concurrent=1)
    ik._load_clipboard_paste_mode()
    assert ik.current_index == 0

    ik._on_paste()                       # simulate one Cmd+V
    assert ik.current_index == 1         # advanced by exactly one chapter
    assert "chapter 2" in clip_text()    # clipboard reloaded with next chapter

    ik._on_paste()
    assert ik.current_index == 2
    assert "chapter 3" in clip_text()


def test_paste_concurrent_advances_by_block(ik):
    configure_paste(ik, prompt_as_text=True, chapter_as_text=True, concurrent=2)
    ik._load_clipboard_paste_mode()
    text = clip_text()
    assert "chapter 1" in text and "chapter 2" in text
    ik._on_paste()
    assert ik.current_index == 2
    assert "chapter 3" in clip_text() and "chapter 4" in clip_text()


# --------------------------------------------------------------------------- #
# PASTE mode — mixed text + files == "true auto-switch clipboard"
# --------------------------------------------------------------------------- #
def test_auto_switch_clipboard_staged_sequence(ik, monkeypatch):
    import inkcopy

    sent = []
    # Don't post a real Cmd+V to the OS during tests.
    monkeypatch.setattr(inkcopy._hotkey_backend, "send_paste", lambda: (sent.append(1) or True))

    configure_paste(ik, prompt_as_text=True, chapter_as_text=False, concurrent=1)
    # Keep timings at their floor so the test is quick but still exercises the chain.
    ik.staged_ms_clipboard_to_ctrl_v = 0
    ik.staged_ms_after_text_paste = 0

    ik._load_clipboard_paste_mode()
    # Step 1: clipboard holds the prompt TEXT, the chapter file is staged.
    assert "professional Thai-to-English" in clip_text()
    assert ik._staged_pending_file_paths and len(ik._staged_pending_file_paths) == 1
    if IS_MAC:
        assert not pb_has_file_url(), "no files on the pasteboard yet — text stage"

    # Step 2: user Cmd+V -> app SWITCHES the real system pasteboard text->files
    # (this is the 'สลับ' the user cares about), fires synthetic Cmd+V, advances.
    ik._on_paste()
    if IS_MAC:
        # _run_staged_file_paste_then_finish wrote the files synchronously, so the
        # real pasteboard has switched to file URLs *right now*, before the paste.
        assert pb_has_file_url(), "clipboard did not switch to files on Cmd+V"
    QTest.qWait(1500)

    assert sent == [1], "synthetic paste should fire exactly once"
    assert ik.current_index == 1, "staged sequence should advance exactly one round"
    assert ik._staged_sequence_active is False
    assert ik._suppress_paste_hotkey is False


@pytest.mark.skipif(not IS_MAC, reason="real pasteboard check is darwin-only")
def test_file_only_writes_real_file_urls(ik):
    """file+file: pasteboard gets real file URLs, no staging, advance on paste."""
    configure_paste(ik, prompt_as_text=False, chapter_as_text=False, concurrent=2)
    ik.include_prompt = False                 # chapters only -> pure file payload
    ik._load_clipboard_paste_mode()
    assert pb_has_file_url(), "file-only paste must put file URLs on the pasteboard"
    assert ik._staged_pending_file_paths is None
    ik._on_paste()
    assert ik.current_index == 2              # advanced by the concurrent block


@pytest.mark.skipif(not IS_MAC, reason="darwin-only")
def test_text_only_no_file_urls(ik):
    """text+text: only text on the pasteboard, never file URLs."""
    configure_paste(ik, prompt_as_text=True, chapter_as_text=True, concurrent=1)
    ik._load_clipboard_paste_mode()
    assert "chapter 1" in clip_text()
    assert not pb_has_file_url()


# --------------------------------------------------------------------------- #
# COPY mode
# --------------------------------------------------------------------------- #
def test_copy_mode_saves_clipboard_to_file(ik, tmp_path):
    configure_copy(ik, str(tmp_path), concurrent=1)
    ik._last_clipboard_text = ""
    ik._ignore_clipboard_change = False

    QApplication.clipboard().setText("TRANSLATED CHAPTER ONE")
    ik._clipboard_check_deferred()        # the 120ms-deferred read, invoked directly

    out_files = list(tmp_path.glob("*.txt"))
    assert len(out_files) == 1
    body = out_files[0].read_text(encoding="utf-8-sig")
    assert "TRANSLATED CHAPTER ONE" in body
    assert ik.current_index == 1          # advanced exactly one chapter


def test_copy_mode_template_off_content_on_first_line(ik, tmp_path):
    """Unchecking the copy-template checkbox saves the copied content starting
    on line 1 (no chapter title) — the option some users want."""
    configure_copy(ik, str(tmp_path), concurrent=1)
    ik.copy_template_enabled = False          # checkbox OFF
    ik._last_clipboard_text = ""
    ik._ignore_clipboard_change = False

    QApplication.clipboard().setText("เนื้อหาบรรทัดแรก CONTENT FIRST")
    ik._clipboard_check_deferred()

    out_files = list(tmp_path.glob("*.txt"))
    assert len(out_files) == 1
    body = out_files[0].read_text(encoding="utf-8-sig")
    assert body.splitlines()[0] == "เนื้อหาบรรทัดแรก CONTENT FIRST"  # content on line 1
    assert "chapter0001" not in body                                   # no title


def test_copy_mode_template_on_title_on_first_line(ik, tmp_path):
    """With the checkbox ON (default), the chapter title is on the first line."""
    configure_copy(ik, str(tmp_path), concurrent=1)
    ik.copy_template_enabled = True
    ik.content_start_line = 3
    ik._last_clipboard_text = ""
    ik._ignore_clipboard_change = False

    QApplication.clipboard().setText("translated body")
    ik._clipboard_check_deferred()

    body = list(tmp_path.glob("*.txt"))[0].read_text(encoding="utf-8-sig")
    assert body.splitlines()[0].startswith("chapter0001")   # title on line 1
    assert "translated body" in body


def test_copy_settings_persist_across_sessions(qapp, tmp_path, monkeypatch):
    """The copy-template choice + content line must survive an app restart."""
    import inkcopy

    monkeypatch.setattr(inkcopy, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(inkcopy, "CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr(inkcopy.SmartClipboardOverlay, "_register_hotkeys", lambda s: None)
    monkeypatch.setattr(inkcopy.SmartClipboardOverlay, "_start_update_check", lambda s: None)
    monkeypatch.setattr(inkcopy.SmartClipboardOverlay, "_start_diagnostics", lambda s: None)

    ov = inkcopy.SmartClipboardOverlay()
    ov.copy_template_checkbox.setChecked(False)   # persists via _save_config
    ov._increase_line()
    ov._increase_line()                           # 3 -> 5, persists
    ov.close()

    ov2 = inkcopy.SmartClipboardOverlay()         # fresh session reloads config
    assert ov2.copy_template_enabled is False
    assert ov2.content_start_line == 5
    assert ov2.copy_template_checkbox.isChecked() is False
    ov2.close()


def test_copy_mode_ignores_self_writes(ik, tmp_path):
    configure_copy(ik, str(tmp_path), concurrent=1)
    ik._ignore_clipboard_change = True    # app is mid-write
    QApplication.clipboard().setText("should be ignored")
    ik._clipboard_check_deferred()
    assert list(tmp_path.glob("*.txt")) == []
    assert ik.current_index == 0


# --------------------------------------------------------------------------- #
# VOCAB mode
# --------------------------------------------------------------------------- #
def test_vocab_mode_appends_entries(ik, tmp_path):
    vocab = tmp_path / "vocab.txt"
    ik.mode = ik.MODE_VOCAB
    ik.vocab_file_path = str(vocab)
    ik.vocab_entry_count = 0
    ik.paused = False

    QApplication.clipboard().setText("คำศัพท์ = vocabulary word")
    ik._on_vocab_clipboard_changed()
    QApplication.clipboard().setText("ดาบ = blade")
    ik._on_vocab_clipboard_changed()

    text = vocab.read_text(encoding="utf-8-sig")
    assert "vocabulary word" in text and "blade" in text
    assert ik.vocab_entry_count == 2


# --------------------------------------------------------------------------- #
# next / prev navigation
# --------------------------------------------------------------------------- #
def test_next_prev_index_math(ik, monkeypatch):
    # _load_clipboard_paste_mode touches the clipboard; stub it to isolate math.
    monkeypatch.setattr(ik, "_load_clipboard_paste_mode", lambda: None)
    configure_paste(ik, prompt_as_text=True, chapter_as_text=True, concurrent=2)

    assert ik.current_index == 0
    ik._go_next()
    assert ik.current_index == 2
    ik._go_next()
    assert ik.current_index == 4
    ik._go_prev()
    assert ik.current_index == 2
    ik._go_prev()
    assert ik.current_index == 0
    ik._go_prev()
    assert ik.current_index == 0          # clamped, never negative


# --------------------------------------------------------------------------- #
# Minimized view keeps prev / pause / next / reset usable
# --------------------------------------------------------------------------- #
def test_minimized_view_has_working_controls(ik, monkeypatch):
    monkeypatch.setattr(ik, "_load_clipboard_paste_mode", lambda: None)
    configure_paste(ik, prompt_as_text=True, chapter_as_text=True, concurrent=1)

    assert ik._mini_controls.isHidden()           # hidden while expanded
    assert not ik._row_diag.isHidden()             # diagnostics visible expanded
    ik._toggle_minimize()
    assert ik.minimized is True
    assert not ik._mini_controls.isHidden()        # shown while minimized
    assert ik.content_widget.isHidden()
    assert ik._row_diag.isHidden()                 # accessibility/log row hidden

    ik.mini_next_btn.click()
    assert ik.current_index == 1                   # next works while minimized
    ik.mini_prev_btn.click()
    assert ik.current_index == 0                   # prev works while minimized

    ik.mini_pause_btn.click()
    assert ik.paused is True
    assert ik.pause_btn.text() == ik.mini_pause_btn.text() == "▶ Resume"  # synced
    ik.mini_pause_btn.click()
    assert ik.paused is False

    ik._toggle_minimize()
    assert ik.minimized is False
    assert ik._mini_controls.isHidden()
    assert not ik.content_widget.isHidden()
    assert not ik._row_diag.isHidden()             # diagnostics back when expanded


# --------------------------------------------------------------------------- #
# macOS COPY/VOCAB pasteboard polling (Qt dataChanged doesn't fire on macOS
# for background copies) — regression for "copy is broken on Mac".
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not IS_MAC, reason="pasteboard polling is darwin-only")
def test_mac_poll_detects_pasteboard_change(ik, monkeypatch):
    from AppKit import NSPasteboard, NSPasteboardTypeString

    fired = []
    monkeypatch.setattr(ik, "_clipboard_data_changed", lambda: fired.append(1))

    ik._last_pasteboard_change_count = ik._read_pasteboard_change_count()
    ik._poll_mac_pasteboard()
    assert fired == []                       # no change yet -> no fire

    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_("external app copy", NSPasteboardTypeString)
    ik._poll_mac_pasteboard()
    assert fired == [1]                       # change detected -> routed once

    ik._poll_mac_pasteboard()
    assert fired == [1]                       # same count -> not refired


@pytest.mark.skipif(not IS_MAC, reason="pasteboard polling is darwin-only")
def test_mac_copy_mode_saves_via_poll(ik, tmp_path):
    from AppKit import NSPasteboard, NSPasteboardTypeString

    configure_copy(ik, str(tmp_path), concurrent=1)
    ik._last_clipboard_text = ""
    ik._ignore_clipboard_change = False
    ik._last_pasteboard_change_count = -999    # force a detected delta

    # Simulate a copy made in ANOTHER app: bump the system pasteboard, and mirror
    # the text into Qt's clipboard (offscreen Qt is decoupled from NSPasteboard).
    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_("POLLED TRANSLATION", NSPasteboardTypeString)
    QApplication.clipboard().setText("POLLED TRANSLATION")

    ik._poll_mac_pasteboard()
    QTest.qWait(200)                           # let the 120ms deferred read fire

    out = list(tmp_path.glob("*.txt"))
    assert len(out) == 1
    assert "POLLED TRANSLATION" in out[0].read_text(encoding="utf-8-sig")
    assert ik.current_index == 1


# --------------------------------------------------------------------------- #
# macOS hotkey double-fire regression
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not IS_MAC, reason="macOS event backend only exists on darwin")
def test_mac_backend_dedups_dual_observers():
    """NSEvent monitor and CGEventTap both observe one physical keypress.
    The handler must fire the callback only ONCE per physical press.
    """
    import inkcopy

    b = inkcopy._MacNSEventBackend()
    counts = {"paste": 0, "next": 0, "prev": 0}
    b._on_paste = lambda: counts.__setitem__("paste", counts["paste"] + 1)
    b._on_next = lambda: counts.__setitem__("next", counts["next"] + 1)
    b._on_prev = lambda: counts.__setitem__("prev", counts["prev"] + 1)

    # One physical Cmd+V reported by BOTH observers in quick succession.
    b._handle_keycode(inkcopy._MAC_KC_V, True, "NSEvent")
    b._handle_keycode(inkcopy._MAC_KC_V, True, "CGEventTap")
    assert counts["paste"] == 1, "Cmd+V double-fired (NSEvent + CGEventTap)"

    # One physical F10 reported by both observers.
    b._handle_keycode(inkcopy._MAC_KC_F10, False, "NSEvent")
    b._handle_keycode(inkcopy._MAC_KC_F10, False, "CGEventTap")
    assert counts["next"] == 1, "F10 double-fired (NSEvent + CGEventTap)"

    # A genuinely separate press later must still register.
    QTest.qWait(120)
    b._handle_keycode(inkcopy._MAC_KC_F10, False, "NSEvent")
    assert counts["next"] == 2, "a later distinct press must not be swallowed"


# --------------------------------------------------------------------------- #
# REAL end-to-end paste ("วางได้จริง"): inject a real Cmd+V into a focused field
# and confirm the text actually lands. Requires a real display + Accessibility,
# so it self-skips in headless/CI and on machines without the grant.
# --------------------------------------------------------------------------- #
def _can_really_paste():
    import inkcopy

    if not IS_MAC:
        return False, "darwin-only"
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return False, "needs a real display (run without QT_QPA_PLATFORM=offscreen)"
    if inkcopy._macos_accessibility_trusted() is not True:
        return False, "Accessibility not granted to this interpreter"
    return True, ""


@pytest.mark.skipif(not IS_MAC, reason="darwin-only")
def test_mac_overlay_does_not_hide_on_deactivate(qapp):
    """The overlay must stay visible when another app (Chrome) is focused.
    Qt::Tool panels hide on deactivate on macOS; the helper must override that."""
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        pytest.skip("needs the cocoa platform (real NSWindow)")
    import inkcopy
    import objc
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QWidget

    w = QWidget()
    w.setWindowFlags(
        Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.WindowStaysOnTopHint
        | Qt.WindowType.Tool
    )
    w.show()
    inkcopy._macos_make_floating_overlay(w)
    win = objc.objc_object(c_void_p=int(w.winId())).window()
    assert win.hidesOnDeactivate() is False
    assert int(win.level()) >= 3                 # floating, above normal windows
    assert int(win.collectionBehavior()) & 1     # canJoinAllSpaces
    w.close()


def test_real_synthetic_paste_into_focused_field(qapp):
    ok, why = _can_really_paste()
    if not ok:
        pytest.skip(why)

    import inkcopy
    from AppKit import NSPasteboard, NSPasteboardTypeString
    from PyQt6.QtWidgets import QPlainTextEdit

    field = QPlainTextEdit()
    field.show()
    field.raise_()
    field.activateWindow()
    field.setFocus()
    QTest.qWait(300)

    payload = "วางได้จริง REAL PASTE 12345"
    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(payload, NSPasteboardTypeString)

    assert inkcopy._cg_send_cmd_v() is True
    QTest.qWait(400)
    QApplication.processEvents()

    assert payload in field.toPlainText(), "synthetic Cmd+V did not land in the field"
    field.close()
