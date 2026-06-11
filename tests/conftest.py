"""Headless test harness for the INKCOPY PyQt6 app.

Runs the *real* SmartClipboardOverlay under Qt's offscreen platform so we can
drive copy / paste / next / prev / auto-switch logic without a display, without
network, and without registering OS-level global hotkeys.
"""
from __future__ import annotations

import os
import sys

# Must be set before PyQt6 is imported anywhere.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

MOCK = os.path.join(ROOT, "mock-data")
PROMPTS_DIR = os.path.join(MOCK, "prompts")
CHAPTERS_DIR = os.path.join(MOCK, "chapters")


@pytest.fixture(scope="session")
def qapp():
    import inkcopy  # noqa: F401  (import after QT_QPA_PLATFORM is set)
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv[:1])
    yield app


@pytest.fixture
def ik(qapp, monkeypatch):
    """A freshly constructed overlay in clean isolation.

    Patched so __init__ does not: load the user's real config, register OS
    global hotkeys, hit the network, or start the diagnostics timer.
    """
    import inkcopy

    monkeypatch.setattr(inkcopy, "load_config", lambda: {})
    monkeypatch.setattr(inkcopy.SmartClipboardOverlay, "_register_hotkeys", lambda self: None)
    monkeypatch.setattr(inkcopy.SmartClipboardOverlay, "_start_update_check", lambda self: None)
    monkeypatch.setattr(inkcopy.SmartClipboardOverlay, "_start_diagnostics", lambda self: None)

    overlay = inkcopy.SmartClipboardOverlay()
    yield overlay
    try:
        overlay.close()
    except Exception:
        pass


def list_files(dirpath):
    """(display_name, abspath) tuples sorted naturally — mirrors the app's scan."""
    from natsort import natsorted

    names = natsorted(n for n in os.listdir(dirpath) if n.endswith(".txt"))
    return [(n, os.path.join(dirpath, n)) for n in names]


def configure_paste(ik, *, prompt_as_text=True, chapter_as_text=False, concurrent=1):
    """Wire the overlay into PASTE mode with the mock prompt + chapter data."""
    ik.mode = ik.MODE_PASTE
    ik.prompt_files = list_files(PROMPTS_DIR)
    ik.chapter_files = list_files(CHAPTERS_DIR)
    ik._chapter_files_all = list(ik.chapter_files)
    ik.include_prompt = True
    ik.include_chapter = True
    ik.concurrent_chapters = concurrent
    ik.current_index = 0
    ik.paused = False
    ik.chapter_paste_as_text = chapter_as_text
    ik.prompt_paste_modes = {dn: prompt_as_text for dn, _ in ik.prompt_files}
    return ik


def configure_copy(ik, output_dir, *, concurrent=1):
    ik.mode = ik.MODE_COPY
    ik.chapter_files = list_files(CHAPTERS_DIR)
    ik._chapter_files_all = list(ik.chapter_files)
    ik.output_folder = output_dir
    ik.concurrent_chapters = concurrent
    ik.current_index = 0
    ik.paused = False
    ik.copy_template_enabled = True
    return ik
