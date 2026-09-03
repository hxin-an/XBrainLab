@echo off
setlocal EnableExtensions

set "XBRAINLAB_REPO_WIN=%~dp0"
set "XBRAINLAB_SETUP_PS1=%XBRAINLAB_REPO_WIN%scripts\launchers\xbrainlab_windows_setup.ps1"

if not exist "%XBRAINLAB_SETUP_PS1%" (
  echo XBrainLab setup script was not found:
  echo   %XBRAINLAB_SETUP_PS1%
  exit /b 1
)

where powershell.exe >nul 2>&1
if errorlevel 1 (
  echo powershell.exe was not found. XBrainLab setup requires Windows PowerShell.
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%XBRAINLAB_SETUP_PS1%" %*
exit /b %ERRORLEVEL%
