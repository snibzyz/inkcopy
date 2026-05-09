@echo off
cd /d "%~dp0"

echo Starting Smart Clipboard...

where python >nul 2>nul
if not errorlevel 1 (
  python "%~dp0smart_clipboard.py"
  goto :after
)

py -3 --version >nul 2>nul
if not errorlevel 1 (
  py -3 "%~dp0smart_clipboard.py"
  goto :after
)

echo ERROR: Python not found. Install Python 3 and run install.bat first.
pause
exit /b 1

:after
if errorlevel 1 (
  echo.
  echo Exited with error. Run install.bat if modules are missing.
  pause
)
