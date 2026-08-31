@echo off
setlocal
cd /d "%~dp0"
title Project Kairos — setup

call scripts\ensure_python.bat
if errorlevel 1 (
  echo.
  pause
  exit /b 1
)

call %KAIROS_PY% scripts\launch.py --setup
echo.
pause
