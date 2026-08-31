@echo off
rem sCure DVT — double-click to start. Uses the repo's virtual environment.
cd /d "%~dp0"
"%~dp0..\.venv\Scripts\python.exe" -m dvt_tool.app %*
