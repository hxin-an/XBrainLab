$ErrorActionPreference = "Stop"

$RepoWindows = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))

function ConvertTo-WslPath {
    param([Parameter(Mandatory = $true)][string]$WindowsPath)

    if ($WindowsPath -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "XBrainLab must be launched from a Windows drive mounted in WSL. Path: $WindowsPath"
    }

    $drive = $Matches[1].ToLowerInvariant()
    $tail = $Matches[2] -replace '\\', '/'
    return "/mnt/$drive/$tail"
}

$Repo = if ($env:XBRAINLAB_WSL_REPO) {
    $env:XBRAINLAB_WSL_REPO
}
else {
    ConvertTo-WslPath $RepoWindows
}
$RepoDrive = Split-Path -Qualifier $RepoWindows
$CacheRootWindows = if ($env:XBRAINLAB_CACHE_ROOT_WIN) {
    [System.IO.Path]::GetFullPath($env:XBRAINLAB_CACHE_ROOT_WIN)
}
else {
    Join-Path "$RepoDrive\" "XBrainLabCache"
}
$CacheRoot = ConvertTo-WslPath $CacheRootWindows
if ($CacheRoot.Contains("'")) {
    throw "The XBrainLab cache path cannot contain a single quote: $CacheRootWindows"
}
$LegacyModelCacheWindows = Join-Path $RepoWindows "XBrainLab\llm\core\models"
$LegacyGraniteCacheWindows = Join-Path `
    $LegacyModelCacheWindows `
    "models--ibm-granite--granite-3.3-2b-instruct"
$ModelCacheWindows = if (
    Test-Path $LegacyGraniteCacheWindows -PathType Container
) {
    $LegacyModelCacheWindows
}
else {
    Join-Path $CacheRootWindows "models"
}
$ModelCache = ConvertTo-WslPath $ModelCacheWindows
$RagCache = "$CacheRoot/rag"
$CacheEnvironment = @"
export XBRAINLAB_MODEL_CACHE_DIR='$ModelCache'
export XBRAINLAB_RAG_CACHE_DIR='$RagCache'
mkdir -p -- '$ModelCache' '$RagCache'
"@
$LogDir = Join-Path $env:LOCALAPPDATA "XBrainLab\logs"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$LauncherLogRetentionCount = 5
$LauncherLogMaxBytes = 1MB

function Remove-ExpiredLauncherLogs {
    Get-ChildItem -Path $LogDir -Filter "launcher-*.log" -File |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -Skip $LauncherLogRetentionCount |
        Remove-Item -Force -ErrorAction SilentlyContinue
}

$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$script:LogFile = Join-Path $LogDir "launcher-$Timestamp.log"
$script:LogLock = New-Object object
$script:LogEncoding = New-Object System.Text.UTF8Encoding($false)

function Write-LauncherConsoleLine {
    param([AllowEmptyString()][string]$Message = "")

    [Console]::Out.WriteLine($Message)
}

function Write-LauncherLine {
    param([AllowEmptyString()][string]$Message = "")

    Write-LauncherConsoleLine $Message
    [System.Threading.Monitor]::Enter($script:LogLock)
    try {
        $payload = "$Message`r`n"
        $existingLength = if (Test-Path $script:LogFile) {
            (Get-Item $script:LogFile).Length
        }
        else {
            0
        }
        if (
            $existingLength + $script:LogEncoding.GetByteCount($payload) -gt
            $LauncherLogMaxBytes
        ) {
            return
        }
        [System.IO.File]::AppendAllText(
            $script:LogFile,
            $payload,
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
        Write-LauncherConsoleLine "Process arguments: $($process.StartInfo.Arguments)"
    }

    [void]$process.Start()
    while ($null -ne ($line = $process.StandardOutput.ReadLine())) {
        # Child output can contain EEG paths, subject identifiers, or native
        # diagnostics that bypass Python redaction. Keep it visible in the
        # terminal, but never persist it in the bounded launcher lifecycle log.
        Write-LauncherConsoleLine $line
    }
    $process.WaitForExit()
    return $process.ExitCode
}

Write-LauncherLine "XBrainLab launcher"
Remove-ExpiredLauncherLogs
Write-LauncherLine "Starting XBrainLab..."
Write-LauncherLine "Geometry diagnostics: set XBRAINLAB_STARTUP_DIAGNOSTICS=1 before launch."
Write-LauncherLine ""
Write-LauncherConsoleLine "Launcher log: $script:LogFile"

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
Write-LauncherConsoleLine "WSL executable: $($Wsl.Source)"

if ($env:XBRAINLAB_LAUNCHER_SMOKE -eq "wsl") {
    $ExitCode = Invoke-WslWithLiveLog `
        -WslPath $Wsl.Source `
        -Command "echo WSL_launcher_smoke_stdout; echo WSL_launcher_smoke_stderr 1>&2"
    exit $ExitCode
}

if ($env:XBRAINLAB_LAUNCHER_SMOKE -eq "startup") {
    $StartupCommand = @"
$CacheEnvironment
set -o pipefail
cd '$Repo'
export PYTHONUNBUFFERED=1
export XBRAINLAB_STARTUP_DIAGNOSTICS=1
echo "WSL repo: `$(pwd)"
echo "Launcher startup smoke: running run.py through the Windows launcher path."
echo "Launcher startup smoke: startup geometry diagnostics enabled."
if command -v xvfb-run >/dev/null 2>&1; then
  echo "Launcher startup smoke: using xvfb-run for deterministic headless capture."
  timeout 45s xvfb-run -a poetry run python run.py --model local
else
  echo "Launcher startup smoke: xvfb-run unavailable; using current display."
  timeout 45s poetry run python run.py --model local
fi
status=`$?
if [ "`$status" = "124" ]; then
  echo "Launcher startup smoke: GUI kept running until timeout."
  exit 0
fi
exit "`$status"
"@
    $ExitCode = Invoke-WslWithLiveLog -WslPath $Wsl.Source -Command $StartupCommand
    exit $ExitCode
}

$Command = @"
$CacheEnvironment
set -o pipefail
cd '$Repo'
export PYTHONUNBUFFERED=1
echo "WSL repo: `$(pwd)"
echo "Python stdout/stderr are mirrored to this terminal and the launcher log."
export PYTHONFAULTHANDLER=1
if [ "`${XBRAINLAB_STARTUP_DIAGNOSTICS:-}" = "1" ]; then
  echo "Startup geometry diagnostics: enabled"
else
  echo "Startup geometry diagnostics: disabled"
fi
if [ -n "`${XBRAINLAB_QT_PLATFORM:-}" ]; then
  export QT_QPA_PLATFORM="`$XBRAINLAB_QT_PLATFORM"
  echo "Qt platform override: `$QT_QPA_PLATFORM"
else
  export QT_QPA_PLATFORM=xcb
  echo "Qt platform override: `$QT_QPA_PLATFORM (launcher default)"
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
    Write-LauncherConsoleLine "Open launcher log: notepad `"$script:LogFile`""
    Read-Host "Press Enter to close"
}

exit $ExitCode
