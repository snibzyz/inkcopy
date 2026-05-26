# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for INKCOPY (cross-platform).
# Build:  python -m PyInstaller --noconfirm --clean INKCOPY.spec
# Output:
#   Windows : dist/INKCOPY.exe   (onefile, windowed, portable)
#   macOS   : dist/INKCOPY.app   (windowed app bundle)

import sys

block_cipher = None
is_macos = sys.platform == "darwin"
is_windows = sys.platform == "win32"

# Platform-specific icon + hidden imports
if is_macos:
    icon_path = "assets/inkcopy.icns"
    bundled_icon = ("assets/inkcopy.icns", ".")
    hidden_imports = [
        "pynput",
        "pynput.keyboard",
        "pynput.keyboard._darwin",
        "pynput._util",
        "pynput._util.darwin",
        "Quartz",
        "AppKit",
        "natsort",
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
    ]
elif is_windows:
    icon_path = "assets/inkcopy.ico"
    bundled_icon = ("assets/inkcopy.ico", ".")
    hidden_imports = [
        "keyboard",
        "natsort",
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
    ]
else:
    icon_path = None
    bundled_icon = ("assets/inkcopy.png", ".")
    hidden_imports = [
        "pynput",
        "pynput.keyboard",
        "natsort",
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
    ]

a = Analysis(
    ["inkcopy.py"],
    pathex=[],
    binaries=[],
    datas=[bundled_icon],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "PyQt6.QtNetwork",
        "PyQt6.QtQml",
        "PyQt6.QtQuick",
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtMultimedia",
        "PyQt6.QtSql",
        "PyQt6.QtTest",
        "PyQt6.Qt3DCore",
    ],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="INKCOPY",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=not is_macos,                 # UPX corrupts macOS bundles — disable on Mac
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,                    # windowed app (no console flash)
    disable_windowed_traceback=False,
    argv_emulation=is_macos,          # macOS Finder drag-drop / "Open with"
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=False,                  # Windows: do NOT request admin
    uac_uiaccess=False,
    icon=icon_path,
)

if is_macos:
    app = BUNDLE(
        exe,
        name="INKCOPY.app",
        icon=icon_path,
        bundle_identifier="com.snibzyz.inkcopy",
        info_plist={
            "CFBundleName": "INKCOPY",
            "CFBundleDisplayName": "INKCOPY",
            "CFBundleShortVersionString": "0.2.1",
            "CFBundleVersion": "0.2.1",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            # Accessibility prompt rationale shown by macOS when asking for permission.
            "NSAppleEventsUsageDescription":
                "INKCOPY synthesizes Cmd+V to paste prompts/chapters into other apps.",
        },
    )
