@echo off
setlocal
cd /d "%~dp0"
title Project Kairos

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
  if not errorlevel 1 (
    ".venv\Scripts\python.exe" scripts\launch.py
    goto :end
  )
)

echo Checking Python…
call scripts\ensure_python.bat
if errorlevel 1 (
  echo.
  pause
  exit /b 1
)

call %KAIROS_PY% scripts\launch.py

:end
echo.
pause
