@echo off
setlocal

set "D=/mnt/d"
set "W=workspace"
set "W=%W%_v2"
set "P=projects"
set "P=%P%/lab"
set "APP=XBrainLab"
set "XBRAINLAB_WSL_REPO=%D%/%W%/%P%/%APP%"
set "XBRAINLAB_LOG_DIR=%LOCALAPPDATA%\XBrainLab\logs"
if not exist "%XBRAINLAB_LOG_DIR%" mkdir "%XBRAINLAB_LOG_DIR%"

for /f "tokens=1-4 delims=/ " %%a in ("%date%") do set "TODAY=%%d-%%b-%%c"
for /f "tokens=1-3 delims=:." %%a in ("%time%") do set "NOW=%%a%%b%%c"
set "NOW=%NOW: =0%"
set "XBRAINLAB_LOG=%XBRAINLAB_LOG_DIR%\launcher-%TODAY%-%NOW%.log"

echo Starting XBrainLab... > "%XBRAINLAB_LOG%"
echo WSL repo: %XBRAINLAB_WSL_REPO% >> "%XBRAINLAB_LOG%"
echo Log: %XBRAINLAB_LOG% >> "%XBRAINLAB_LOG%"

where wsl.exe >nul 2>&1
if errorlevel 1 (
  echo wsl.exe was not found. Install or enable Windows Subsystem for Linux. >> "%XBRAINLAB_LOG%"
  type "%XBRAINLAB_LOG%"
  pause
  exit /b 1
)

wsl.exe -e bash -lc "cd '%XBRAINLAB_WSL_REPO%' && export PYTHONUNBUFFERED=1 && if command -v poetry >/dev/null 2>&1; then poetry run python run.py; elif [ -x /home/administrator/.local/bin/poetry ]; then /home/administrator/.local/bin/poetry run python run.py; else python run.py; fi" >> "%XBRAINLAB_LOG%" 2>&1
set "XBRAINLAB_EXIT=%ERRORLEVEL%"

if not "%XBRAINLAB_EXIT%"=="0" (
  echo. >> "%XBRAINLAB_LOG%"
  echo XBrainLab exited with code %XBRAINLAB_EXIT%. >> "%XBRAINLAB_LOG%"
  type "%XBRAINLAB_LOG%"
  pause
)

exit /b %XBRAINLAB_EXIT%
