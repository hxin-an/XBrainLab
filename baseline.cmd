@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "XBL_BASELINE_PYTHON=%~dp0..\XBrainLab\.venv\Scripts\python.exe"
if not exist "%XBL_BASELINE_PYTHON%" (
  echo Existing shared Windows Python is missing. No environment will be installed automatically.
  exit /b 1
)
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
"%XBL_BASELINE_PYTHON%" "%~dp0scripts\dev\run_assistant_baseline.py" %*
exit /b %ERRORLEVEL%
