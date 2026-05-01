$ErrorActionPreference = "Stop"

$Repo = "/mnt/d/workspace_v2/projects/lab/XBrainLab"
$LogDir = Join-Path $env:LOCALAPPDATA "XBrainLab\logs"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LogFile = Join-Path $LogDir "launcher-$Timestamp.log"

"Starting XBrainLab..." | Out-File -FilePath $LogFile -Encoding utf8
"WSL repo: $Repo" | Out-File -FilePath $LogFile -Encoding utf8 -Append
"Log: $LogFile" | Out-File -FilePath $LogFile -Encoding utf8 -Append

$Wsl = Get-Command "wsl.exe" -ErrorAction SilentlyContinue
if ($null -eq $Wsl) {
    "wsl.exe was not found. Install or enable Windows Subsystem for Linux." |
        Out-File -FilePath $LogFile -Encoding utf8 -Append
    Get-Content $LogFile
    Read-Host "Press Enter to close"
    exit 1
}

$Command = @"
cd '$Repo' &&
export PYTHONUNBUFFERED=1 &&
if command -v poetry >/dev/null 2>&1; then
  poetry run python run.py
elif [ -x /home/administrator/.local/bin/poetry ]; then
  /home/administrator/.local/bin/poetry run python run.py
else
  python run.py
fi
"@

& $Wsl.Source -e bash -lc $Command *>> $LogFile
$ExitCode = $LASTEXITCODE

if ($ExitCode -ne 0) {
    "" | Out-File -FilePath $LogFile -Encoding utf8 -Append
    "XBrainLab exited with code $ExitCode." | Out-File -FilePath $LogFile -Encoding utf8 -Append
    Get-Content $LogFile
    Read-Host "Press Enter to close"
}

exit $ExitCode
