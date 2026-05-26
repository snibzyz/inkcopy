; INKCOPY NSIS installer - modeled after the electron-builder "oneClick" preset
; used by INKTTS / INKCRAW / INKIDEA in this workspace.
;
;   - per-user install (no UAC prompt) to %LOCALAPPDATA%\Programs\INKCOPY
;   - Start Menu + Desktop shortcuts
;   - silent install supported via /S (used by the in-app auto-updater)
;   - leaves %APPDATA%\INKCOPY\config.json untouched on uninstall
;   - kills any running INKCOPY.exe before replacing the binary
;
; Build:
;   makensis /DAPP_VERSION=0.2.0 scripts\installer.nsi
; (scripts\build_nsis.bat reads the version from inkcopy.py and invokes this.)

!ifndef APP_VERSION
  !define APP_VERSION "0.0.0"
!endif

!define APP_NAME       "INKCOPY"
!define APP_PUBLISHER  "snibzyz"
!define APP_EXE        "INKCOPY.exe"
!define APP_URL        "https://github.com/snibzyz/inkcopy"
!define UNINST_KEY     "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"

Name "${APP_NAME} ${APP_VERSION}"
OutFile "..\dist\INKCOPY-Setup-${APP_VERSION}.exe"

; Per-user install - no admin prompt. Matches INK family convention.
RequestExecutionLevel user
InstallDir "$LOCALAPPDATA\Programs\${APP_NAME}"
InstallDirRegKey HKCU "Software\${APP_NAME}" "InstallDir"

SetCompressor /SOLID lzma
ShowInstDetails show
ShowUninstDetails show

VIProductVersion "${APP_VERSION}.0"
VIAddVersionKey "ProductName"     "${APP_NAME}"
VIAddVersionKey "FileDescription" "${APP_NAME} Installer"
VIAddVersionKey "FileVersion"     "${APP_VERSION}"
VIAddVersionKey "ProductVersion"  "${APP_VERSION}"
VIAddVersionKey "CompanyName"     "${APP_PUBLISHER}"
VIAddVersionKey "LegalCopyright"  "(c) ${APP_PUBLISHER}"

!include "MUI2.nsh"
!include "FileFunc.nsh"

!define MUI_ICON   "..\assets\inkcopy.ico"
!define MUI_UNICON "..\assets\inkcopy.ico"

; oneClick-style flow: show progress page only, then finish + auto-launch.
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "Launch ${APP_NAME}"

!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; --- helper: kill a running INKCOPY.exe so the file isn't locked ---
!macro KillRunning
  ; nsExec to suppress window; ignore errors (process may not be running).
  nsExec::Exec 'taskkill /F /IM "${APP_EXE}"'
  Sleep 400
!macroend

Section "Install"
  SetOutPath "$INSTDIR"

  !insertmacro KillRunning

  ; Bring the freshly-built portable .exe in. PyInstaller --onefile emits a single
  ; INKCOPY.exe in dist/; build_nsis.bat copies it next to this .nsi before makensis.
  File "..\dist\${APP_EXE}"

  ; --- shortcuts (Start Menu + Desktop, matching INKTTS oneClick layout) ---
  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortcut  "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
  CreateShortcut  "$SMPROGRAMS\${APP_NAME}\Uninstall ${APP_NAME}.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut  "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"

  ; --- uninstaller + registry entries for Programs & Features ---
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\${APP_NAME}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\${APP_NAME}" "Version"    "${APP_VERSION}"

  WriteRegStr   HKCU "${UNINST_KEY}" "DisplayName"     "${APP_NAME}"
  WriteRegStr   HKCU "${UNINST_KEY}" "DisplayVersion"  "${APP_VERSION}"
  WriteRegStr   HKCU "${UNINST_KEY}" "Publisher"       "${APP_PUBLISHER}"
  WriteRegStr   HKCU "${UNINST_KEY}" "URLInfoAbout"    "${APP_URL}"
  WriteRegStr   HKCU "${UNINST_KEY}" "DisplayIcon"     "$INSTDIR\${APP_EXE}"
  WriteRegStr   HKCU "${UNINST_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr   HKCU "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegStr   HKCU "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1

  ; ARP "EstimatedSize" in KB
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKCU "${UNINST_KEY}" "EstimatedSize" "$0"
SectionEnd

Section "Uninstall"
  !insertmacro KillRunning

  Delete "$INSTDIR\${APP_EXE}"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir  "$INSTDIR"

  Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\Uninstall ${APP_NAME}.lnk"
  RMDir  "$SMPROGRAMS\${APP_NAME}"
  Delete "$DESKTOP\${APP_NAME}.lnk"

  DeleteRegKey HKCU "Software\${APP_NAME}"
  DeleteRegKey HKCU "${UNINST_KEY}"

  ; NOTE: %APPDATA%\INKCOPY\config.json is intentionally preserved so settings
  ; survive an update (auto-updater runs the uninstaller + new installer).
SectionEnd
