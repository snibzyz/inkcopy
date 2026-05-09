@echo off
setlocal enabledelayedexpansion
set "ROOT=%~dp0.."
cd /d "%ROOT%"

echo ============================================================
echo  Building INKCOPY.exe (portable, onefile)
echo ============================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo         Install Python 3 from https://www.python.org/downloads/
    pause
    exit /b 1
)

python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    python -m pip install --upgrade pyinstaller
    if errorlevel 1 (
        echo [ERROR] Failed to install PyInstaller.
        pause
        exit /b 1
    )
)

echo Installing/updating runtime dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install runtime dependencies.
    pause
    exit /b 1
)
echo.

echo Cleaning previous build artifacts...
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist
echo.

echo Running PyInstaller...
python -m PyInstaller --noconfirm --clean INKCOPY.spec
if errorlevel 1 (
    echo.
    echo [ERROR] Build FAILED.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Build OK
echo ============================================================
echo  Output : %CD%\dist\INKCOPY.exe
echo  Usage  : copy INKCOPY.exe to any folder and run it.
echo           config saved to %%APPDATA%%\INKCOPY\config.json.
echo ============================================================
echo.
pause
