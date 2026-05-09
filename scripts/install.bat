@echo off
setlocal
set "ROOT=%~dp0.."
cd /d "%ROOT%"

echo =========================================
echo   INKCOPY - install dependencies
echo =========================================
echo.

where python >nul 2>nul
if not errorlevel 1 (
  python -m pip install -r "%ROOT%\requirements.txt"
  if errorlevel 1 goto :fail
  goto :ok
)

py -3 -m pip install -r "%ROOT%\requirements.txt"
if errorlevel 1 goto :fail

:ok
echo.
echo Done. Run: scripts\run.bat
echo.
pause
exit /b 0

:fail
echo.
echo ERROR: pip install failed. Check Python is installed and on PATH.
pause
exit /b 1
