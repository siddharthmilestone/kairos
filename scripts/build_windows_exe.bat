@echo off
setlocal
cd /d "%~dp0\.."
title Build Kairos.exe

if not exist ".venv\Scripts\python.exe" (
  echo Run setup.bat first so .venv exists.
  exit /b 1
)

echo Installing PyInstaller…
".venv\Scripts\python.exe" -m pip install --quiet pyinstaller
if errorlevel 1 exit /b 1

echo Building Kairos.exe…
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean scripts\kairos.spec
if errorlevel 1 exit /b 1

if not exist "dist\Kairos.exe" (
  echo Build finished but dist\Kairos.exe was not found.
  exit /b 1
)

copy /Y "dist\Kairos.exe" "Kairos.exe" >nul
echo.
echo Created Kairos.exe in this folder.
echo Double-click Kairos.exe after setup.bat has been run on this PC.
echo Keep Kairos.exe next to app.py and .venv — do not copy the exe alone.
