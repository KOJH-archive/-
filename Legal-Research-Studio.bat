@echo off
setlocal
cd /d "%~dp0"
title Korean Legal Research Studio
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 goto failed
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m legal_studio.launcher %*
if errorlevel 1 goto failed
exit /b 0
:failed
echo Launch failed. See the message above.
pause
exit /b 1
