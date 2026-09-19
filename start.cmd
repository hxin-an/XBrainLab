@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" || exit /b 1

if not exist ".venv\Scripts\python.exe" goto missing_python

set "QT_QPA_PLATFORM=windows"
if not defined XBRAINLAB_MODEL_CACHE_DIR if exist "D:\XBrainLabCache\models\" set "XBRAINLAB_MODEL_CACHE_DIR=D:\XBrainLabCache\models"
if not defined XBRAINLAB_RAG_CACHE_DIR if exist "D:\XBrainLabCache\rag\" set "XBRAINLAB_RAG_CACHE_DIR=D:\XBrainLabCache\rag"
set "HF_HUB_OFFLINE=1"
set "TRANSFORMERS_OFFLINE=1"

".venv\Scripts\python.exe" "run.py" %*
set "XBL_LAUNCH_EXIT=%ERRORLEVEL%"
popd
exit /b %XBL_LAUNCH_EXIT%

:missing_python
echo Windows Python is missing: "%CD%\.venv\Scripts\python.exe"
echo Run setup-windows.cmd explicitly to install the environment first.
popd
exit /b 1
