@echo off
setlocal EnableExtensions

set "D=/mnt/d"
set "W=work"
set "W=%W%space"
set "W=%W%_v2"
set "P=proj"
set "P=%P%ects"
set "P=%P%/lab"
set "P=%P%/XBrainLab"
set "XBRAINLAB_WSL_REPO=%D%/%W%/%P%"
set "XW=D:\work"
set "XW=%XW%space"
set "XW=%XW%_v2"
set "XP=proj"
set "XP=%XP%ects"
set "XBRAINLAB_REPO_WIN=%XW%\%XP%\lab\XBrainLab"
set "XBRAINLAB_PS1=%XBRAINLAB_REPO_WIN%\scripts\launchers\xbrainlab_wsl_launcher.ps1"

echo XBrainLab launcher bootstrap
echo Active WSL repo: %XBRAINLAB_WSL_REPO%
echo Active Windows repo: %XBRAINLAB_REPO_WIN%
echo PowerShell launcher: %XBRAINLAB_PS1%
echo Starting PowerShell launcher...
echo.

where powershell.exe >nul 2>&1
if errorlevel 1 (
  echo powershell.exe was not found. Cannot start XBrainLab launcher.
  pause
  exit /b 1
)

if not exist "%XBRAINLAB_PS1%" (
  echo Launcher script was not found:
  echo   %XBRAINLAB_PS1%
  echo This desktop command is expected to delegate to the active repo, not a generated stale app.
  pause
  exit /b 1
)

if "%XBRAINLAB_LAUNCHER_SMOKE%"=="1" (
  echo Launcher smoke mode: PowerShell launcher exists; WSL launch skipped.
  exit /b 0
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%XBRAINLAB_PS1%"
set "XBRAINLAB_EXIT=%ERRORLEVEL%"

if not "%XBRAINLAB_EXIT%"=="0" (
  echo.
  echo XBrainLab launcher exited with code %XBRAINLAB_EXIT%.
  pause
)

exit /b %XBRAINLAB_EXIT%
