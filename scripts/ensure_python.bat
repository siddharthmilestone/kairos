@echo off
REM Find Python 3.9+ or install it (Windows). Sets KAIROS_PY for the caller.
REM Usage:  call scripts\ensure_python.bat
REM         if errorlevel 1 exit /b 1
REM         call %KAIROS_PY% scripts\launch.py

set "KAIROS_PY="

call :find_python
if defined KAIROS_PY goto :ok

echo.
echo Python 3.9+ was not found. Installing Python 3.12 (one-time^)...
echo You may see a Windows permission prompt. Accept it to continue.
echo.
call :install_python
call :add_typical_paths
call :find_python
if defined KAIROS_PY goto :ok

echo.
echo Could not install Python automatically.
echo Install it from https://www.python.org/downloads/
echo Tick "Add python.exe to PATH", then double-click Kairos.bat again.
exit /b 1

:ok
echo Using Python: %KAIROS_PY%
exit /b 0


:find_python
where py >nul 2>&1
if %ERRORLEVEL%==0 (
  py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
  if not errorlevel 1 (
    set "KAIROS_PY=py -3"
    exit /b 0
  )
)
where python >nul 2>&1
if %ERRORLEVEL%==0 (
  python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
  if not errorlevel 1 (
    set "KAIROS_PY=python"
    exit /b 0
  )
)
where python3 >nul 2>&1
if %ERRORLEVEL%==0 (
  python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
  if not errorlevel 1 (
    set "KAIROS_PY=python3"
    exit /b 0
  )
)
if exist "%LocalAppData%\Programs\Python\Launcher\py.exe" (
  "%LocalAppData%\Programs\Python\Launcher\py.exe" -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
  if not errorlevel 1 (
    set "KAIROS_PY=%LocalAppData%\Programs\Python\Launcher\py.exe -3"
    exit /b 0
  )
)
for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do (
  if exist "%%D\python.exe" (
    "%%D\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
    if not errorlevel 1 (
      set "PATH=%%D;%%D\Scripts;%PATH%"
      set "KAIROS_PY=%%D\python.exe"
      exit /b 0
    )
  )
)
for /d %%D in ("%ProgramFiles%\Python3*") do (
  if exist "%%D\python.exe" (
    "%%D\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
    if not errorlevel 1 (
      set "PATH=%%D;%%D\Scripts;%PATH%"
      set "KAIROS_PY=%%D\python.exe"
      exit /b 0
    )
  )
)
exit /b 1


:add_typical_paths
set "PATH=%LocalAppData%\Programs\Python\Python312;%LocalAppData%\Programs\Python\Python312\Scripts;%LocalAppData%\Programs\Python\Python313;%LocalAppData%\Programs\Python\Python313\Scripts;%LocalAppData%\Programs\Python\Launcher;%PATH%"
exit /b 0


:install_python
where winget >nul 2>&1
if %ERRORLEVEL%==0 (
  echo Trying winget…
  winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
  if not errorlevel 1 exit /b 0
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  if not errorlevel 1 exit /b 0
)

echo winget did not install Python. Downloading the official installer…
set "KAIROS_PY_INST=%TEMP%\kairos-python-3.12.10-amd64.exe"
curl.exe -L --fail -o "%KAIROS_PY_INST%" "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
if errorlevel 1 (
  echo Download failed. Check your network and try again.
  exit /b 1
)
"%KAIROS_PY_INST%" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_test=0 Include_launcher=1 SimpleInstall=1
exit /b %ERRORLEVEL%
