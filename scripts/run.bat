@echo off
setlocal
set "ROOT=%~dp0.."
cd /d "%ROOT%"

echo Starting INKCOPY...

where python >nul 2>nul
if not errorlevel 1 (
  python "%ROOT%\smart_clipboard.py"
  goto :after
)

py -3 --version >nul 2>nul
if not errorlevel 1 (
  py -3 "%ROOT%\smart_clipboard.py"
  goto :after
)

echo ERROR: Python not found. Install Python 3 and run scripts\install.bat first.
pause
exit /b 1

:after
if errorlevel 1 (
  echo.
  echo Exited with error. Run scripts\install.bat if modules are missing.
  pause
)
