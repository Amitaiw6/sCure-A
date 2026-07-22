@echo off
rem =============================================================
rem sCure Box -- Windows launcher: opens the software FULLSCREEN
rem in its own window (a real app window, not a browser).
rem Double-click this file (or the desktop shortcut) to launch.
rem First run creates a Python venv and installs the server deps
rem (simulation mode -- no IO board needed off the Pi).
rem =============================================================
setlocal
cd /d "%~dp0.."

rem ---- Python venv + dependencies (installs only when missing) ----
if not exist ".venv\Scripts\python.exe" (
  echo [sCure] First run: creating the Python environment...
  python -m venv .venv
  if errorlevel 1 goto :nopython
)
.venv\Scripts\python.exe -c "import flask, flask_cors, webview" >nul 2>&1
if errorlevel 1 (
  echo [sCure] Installing dependencies...
  .venv\Scripts\python.exe -m pip install --quiet flask==3.1.0 flask-cors==5.0.1 pywebview
)

rem ---- Built UI (dist\) ---------------------------------------
if not exist "dist\index.html" (
  echo [sCure] Building the UI ^(one-time, a few minutes^)...
  call npm install
  call npm run build
)

rem ---- Launch the app: server + fullscreen window, no console ----
start "" ".venv\Scripts\pythonw.exe" server\desktop.py
exit /b 0

:nopython
echo [sCure] ERROR: Python not found. Install Python 3 from python.org and retry.
pause
exit /b 1