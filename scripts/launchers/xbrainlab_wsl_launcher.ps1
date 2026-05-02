$ErrorActionPreference = "Stop"

$Workspace = "workspace" + "_v2"
$Repo = ("/mnt/d", $Workspace, "projects", "lab", "XBrainLab") -join "/"
$LogDir = Join-Path $env:LOCALAPPDATA "XBrainLab\logs"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$script:LogFile = Join-Path $LogDir "launcher-$Timestamp.log"
$script:LogLock = New-Object object
$script:LogEncoding = New-Object System.Text.UTF8Encoding($false)

function Write-LauncherLine {
    param([AllowEmptyString()][string]$Message = "")

    [Console]::Out.WriteLine($Message)
    [System.Threading.Monitor]::Enter($script:LogLock)
    try {
        [System.IO.File]::AppendAllText(
            $script:LogFile,
            "$Message`r`n",
            $script:LogEncoding
        )
    }
    finally {
        [System.Threading.Monitor]::Exit($script:LogLock)
    }
}

function ConvertTo-WindowsArgument {
    param([Parameter(Mandatory = $true)][string]$Argument)

    if ($Argument -notmatch '[\s"]') {
        return $Argument
    }

    $escaped = $Argument -replace '(\\*)"', '$1$1\"'
    $escaped = $escaped -replace '(\\+)$', '$1$1'
    return '"' + $escaped + '"'
}

function Invoke-WslWithLiveLog {
    param(
        [Parameter(Mandatory = $true)][string]$WslPath,
        [Parameter(Mandatory = $true)][string]$Command
    )

    $mergedCommand = "exec 2>&1`n$Command"
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo.FileName = $WslPath
    $process.StartInfo.UseShellExecute = $false
    $process.StartInfo.RedirectStandardOutput = $true
    $process.StartInfo.RedirectStandardError = $false
    $process.StartInfo.CreateNoWindow = $false
    $arguments = @("-e", "bash", "-lc", $mergedCommand) |
        ForEach-Object { ConvertTo-WindowsArgument $_ }
    $process.StartInfo.Arguments = $arguments -join " "
    if ($env:XBRAINLAB_LAUNCHER_DEBUG_ARGS -eq "1") {
        Write-LauncherLine "Process arguments: $($process.StartInfo.Arguments)"
    }

    [void]$process.Start()
    while ($null -ne ($line = $process.StandardOutput.ReadLine())) {
        Write-LauncherLine $line
    }
    $process.WaitForExit()
    return $process.ExitCode
}

Write-LauncherLine "XBrainLab launcher"
Write-LauncherLine "Starting XBrainLab..."
Write-LauncherLine "WSL repo: $Repo"
Write-LauncherLine "Log: $script:LogFile"
Write-LauncherLine "Open log: notepad `"$script:LogFile`""
Write-LauncherLine "Follow log: powershell -NoProfile -Command `"Get-Content -Wait '$script:LogFile'`""
Write-LauncherLine "Geometry diagnostics: set XBRAINLAB_STARTUP_DIAGNOSTICS=1 before launch."
Write-LauncherLine ""

if ($env:XBRAINLAB_LAUNCHER_SMOKE -eq "1") {
    Write-LauncherLine "Launcher smoke mode: WSL launch skipped."
    exit 0
}

$Wsl = Get-Command "wsl.exe" -ErrorAction SilentlyContinue
if ($null -eq $Wsl) {
    Write-LauncherLine "wsl.exe was not found. Install or enable Windows Subsystem for Linux."
    Read-Host "Press Enter to close"
    exit 1
}
Write-LauncherLine "WSL executable: $($Wsl.Source)"

if ($env:XBRAINLAB_LAUNCHER_SMOKE -eq "wsl") {
    $ExitCode = Invoke-WslWithLiveLog `
        -WslPath $Wsl.Source `
        -Command "echo WSL_launcher_smoke_stdout; echo WSL_launcher_smoke_stderr 1>&2"
    exit $ExitCode
}

$Command = @"
set -o pipefail
cd '$Repo'
export PYTHONUNBUFFERED=1
echo "WSL repo: `$(pwd)"
echo "Python stdout/stderr are mirrored to this terminal and the launcher log."
if [ "`${XBRAINLAB_STARTUP_DIAGNOSTICS:-}" = "1" ]; then
  echo "Startup geometry diagnostics: enabled"
else
  echo "Startup geometry diagnostics: disabled"
fi
if command -v poetry >/dev/null 2>&1; then
  echo "Launching: poetry run python run.py"
  exec poetry run python run.py
elif [ -x /home/administrator/.local/bin/poetry ]; then
  echo "Launching: /home/administrator/.local/bin/poetry run python run.py"
  exec /home/administrator/.local/bin/poetry run python run.py
else
  echo "Launching: python run.py"
  exec python run.py
fi
"@

$ExitCode = Invoke-WslWithLiveLog -WslPath $Wsl.Source -Command $Command

if ($ExitCode -ne 0) {
    Write-LauncherLine ""
    Write-LauncherLine "XBrainLab exited with code $ExitCode."
    Write-LauncherLine "Open log: notepad `"$script:LogFile`""
    Read-Host "Press Enter to close"
}

exit $ExitCode
