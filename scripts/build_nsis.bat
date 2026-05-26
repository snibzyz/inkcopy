@echo off
setlocal enabledelayedexpansion
set "ROOT=%~dp0.."
cd /d "%ROOT%"

echo ============================================================
echo  Building INKCOPY-Setup-X.X.X.exe (NSIS installer)
echo ============================================================
echo.

REM --- locate makensis.exe -----------------------------------------------------
set "MAKENSIS="
if exist "%ProgramFiles(x86)%\NSIS\makensis.exe" set "MAKENSIS=%ProgramFiles(x86)%\NSIS\makensis.exe"
if exist "%ProgramFiles%\NSIS\makensis.exe"      set "MAKENSIS=%ProgramFiles%\NSIS\makensis.exe"
if "%MAKENSIS%"=="" (
    where makensis.exe >nul 2>&1
    if not errorlevel 1 set "MAKENSIS=makensis.exe"
)
if "%MAKENSIS%"=="" (
    echo [ERROR] makensis.exe not found.
    echo         Install NSIS from https://nsis.sourceforge.io/Download
    echo         or via:  winget install NSIS.NSIS
    pause
    exit /b 1
)
echo Using NSIS: %MAKENSIS%
echo.

REM --- read __version__ from inkcopy.py ---------------------------------------
for /f "usebackq tokens=*" %%v in (`python -c "import re; print(re.search(r'__version__\s*=\s*\"([^\"]+)\"', open('inkcopy.py', encoding='utf-8').read()).group(1))"`) do set "APP_VERSION=%%v"
if "%APP_VERSION%"=="" (
    echo [ERROR] Could not parse __version__ from inkcopy.py
    pause
    exit /b 1
)
echo Version: %APP_VERSION%
echo.

REM --- make sure the portable .exe exists before bundling it -------------------
if not exist "%ROOT%\dist\INKCOPY.exe" (
    echo Portable INKCOPY.exe not found, running scripts\build.bat first...
    call "%ROOT%\scripts\build.bat"
    if errorlevel 1 (
        echo [ERROR] Portable build failed.
        pause
        exit /b 1
    )
)

REM --- compile NSIS ------------------------------------------------------------
echo Compiling NSIS installer...
"%MAKENSIS%" /DAPP_VERSION=%APP_VERSION% "%ROOT%\scripts\installer.nsi"
if errorlevel 1 (
    echo [ERROR] NSIS compile failed.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  NSIS installer OK
echo ============================================================
echo  Output : %ROOT%\dist\INKCOPY-Setup-%APP_VERSION%.exe
echo  Silent : INKCOPY-Setup-%APP_VERSION%.exe /S   (used by auto-updater)
echo ============================================================
echo.
pause
