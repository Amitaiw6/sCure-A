@echo off
REM Launches the sCure UI build locally so the designer can click through every screen.
REM Requires Node.js (https://nodejs.org). The browser opens automatically once ready.
REM Press Ctrl+C or close this window to stop.
cd /d "%~dp0"

REM Find Node: first on PATH, then the common install locations (double-clicked
REM .cmd files sometimes run without Node on PATH even when it is installed).
set "NODE_EXE="
where node >nul 2>nul && set "NODE_EXE=node"
if not defined NODE_EXE if exist "%ProgramFiles%\nodejs\node.exe" set "NODE_EXE=%ProgramFiles%\nodejs\node.exe"
if not defined NODE_EXE if exist "%ProgramFiles(x86)%\nodejs\node.exe" set "NODE_EXE=%ProgramFiles(x86)%\nodejs\node.exe"
if not defined NODE_EXE if exist "%LOCALAPPDATA%\Programs\nodejs\node.exe" set "NODE_EXE=%LOCALAPPDATA%\Programs\nodejs\node.exe"

if not defined NODE_EXE (
  echo.
  echo   Node.js was not found. Install it once from https://nodejs.org then run this again.
  echo.
  pause
  exit /b 1
)

"%NODE_EXE%" "%~dp0server.mjs"
pause
