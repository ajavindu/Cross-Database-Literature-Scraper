@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================
echo   Literature Search - Windows launcher
echo ============================================

set "APPDIR=%~dp0app"
set "MINPYINFO=needs Python 3.9 or newer"

REM ---- 1. Find a COMPATIBLE Python (3.9+) ----------------------------
set "PY="
call :try_python py
if not defined PY call :try_python python
if not defined PY call :try_python python3

REM ---- 2. If none compatible, try to install a modern Python ---------
if not defined PY (
  echo No compatible Python found ^(%MINPYINFO%^). Trying to install with winget...
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
  echo.
  echo If Python was just installed, please CLOSE this window and double-click
  echo run_windows.bat again so Windows can find it.
  call :try_python py
  if not defined PY call :try_python python
)

if not defined PY (
  echo.
  echo Could not find or install a compatible Python ^(%MINPYINFO%^).
  echo Install Python 3 from https://www.python.org/downloads/ ^(TICK "Add to PATH"^),
  echo then re-run this file.
  pause
  exit /b 1
)

echo Using Python: %PY%

REM ---- 3. Create the virtual environment (the "container") -----------
if not exist "%APPDIR%\.venv\Scripts\python.exe" (
  echo Creating virtual environment...
  %PY% -m venv "%APPDIR%\.venv"
)
set "VENVPY=%APPDIR%\.venv\Scripts\python.exe"

REM ---- 4. Install required packages (only the first time) -----------
if not exist "%APPDIR%\.venv\.installed" (
  echo Installing required packages (one-time)...
  "%VENVPY%" -m pip install --upgrade pip
  "%VENVPY%" -m pip install -r "%APPDIR%\requirements.txt"
  if errorlevel 1 (
    echo.
    echo Package installation failed. Check your internet connection and re-run.
    pause
    exit /b 1
  )
  echo done > "%APPDIR%\.venv\.installed"
)

REM ---- 5. Start the app ---------------------------------------------
echo Starting the app... a browser tab will open shortly.
"%VENVPY%" "%APPDIR%\app.py"

pause
exit /b 0

REM ===================================================================
:try_python
REM %1 = candidate command. Sets PY only if it exists AND is >= 3.9.
where %1 >nul 2>&1 || goto :eof
%1 -c "import sys; sys.exit(0 if sys.version_info>=(3,9) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=%1"
goto :eof
