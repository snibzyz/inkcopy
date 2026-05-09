# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for INKCOPY
# Build:  python -m PyInstaller --noconfirm --clean INKCOPY.spec
# Output: dist/INKCOPY.exe   (onefile, windowed, portable)

block_cipher = None

a = Analysis(
    ['inkcopy.py'],
    pathex=[],
    binaries=[],
    datas=[('assets/inkcopy.ico', '.')],
    hiddenimports=[
        'keyboard',
        'natsort',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'PyQt6.QtNetwork',
        'PyQt6.QtQml',
        'PyQt6.QtQuick',
        'PyQt6.QtWebEngineCore',
        'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtMultimedia',
        'PyQt6.QtSql',
        'PyQt6.QtTest',
        'PyQt6.Qt3DCore',
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
    name='INKCOPY',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,                # windowed app (no console flash)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=False,              # do NOT request admin
    uac_uiaccess=False,
    icon='assets/inkcopy.ico',
)
