@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
if exist "%SCRIPT_DIR%inkcopy.py" (
  set "ROOT=%SCRIPT_DIR%"
) else (
  set "ROOT=%~dp0.."
)
cd /d "%ROOT%"

echo ============================================================
echo  Starting INKCOPY Python
echo ============================================================
echo.

set "PYTHON_CMD="
where python >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=python"

if not defined PYTHON_CMD (
  py -3 --version >nul 2>nul
  if not errorlevel 1 set "PYTHON_CMD=py -3"
)

if not defined PYTHON_CMD (
  echo ERROR: Python 3 not found.
  echo Install Python 3 from https://www.python.org/downloads/
  echo During install, enable "Add python.exe to PATH".
  echo.
  pause
  exit /b 1
)

set "VENV_PY=%ROOT%\.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo Creating local Python environment...
  %PYTHON_CMD% -m venv "%ROOT%\.venv"
  if errorlevel 1 (
    echo.
    echo ERROR: Failed to create .venv.
    pause
    exit /b 1
  )
)

"%VENV_PY%" -c "import importlib.util; missing=[pkg for mod,pkg in [('natsort','natsort'),('PyQt6','PyQt6'),('pynput','pynput')] if importlib.util.find_spec(mod) is None]; print('MISSING_DEPS:' + ' '.join(missing)) if missing else None; raise SystemExit(42 if missing else 0)"

if errorlevel 42 (
  echo.
  echo Installing Python dependencies...
  "%VENV_PY%" -m pip install --upgrade pip
  if errorlevel 1 goto :pip_fail
  "%VENV_PY%" -m pip install -r "%ROOT%\requirements.txt"
  if errorlevel 1 goto :pip_fail
)

"%VENV_PY%" "%ROOT%\inkcopy.py"
if errorlevel 1 (
  echo.
  echo INKCOPY exited with an error.
  pause
  exit /b 1
)

exit /b 0

:pip_fail
echo.
echo ERROR: pip install failed. Check your Python installation and internet connection.
pause
exit /b 1
