[CmdletBinding()]
param(
    [switch]$Cpu,
    [switch]$Yes,
    [switch]$NoLaunch,
    [switch]$PlanOnly
)

$ErrorActionPreference = "Stop"

function Get-Python312 {
    $py = Get-Command "py.exe" -ErrorAction SilentlyContinue
    if ($null -ne $py) {
        try {
            $candidate = (& $py.Source -3.12 -c "import platform,sys; print(sys.executable); print(platform.architecture()[0])" 2>$null)
            if ($LASTEXITCODE -eq 0 -and $candidate.Count -ge 2 -and $candidate[1] -eq "64bit") {
                return $candidate[0]
            }
        }
        catch {
            # Fall through to the conventional per-user installation location.
        }
    }

    $candidate = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
    if (Test-Path $candidate -PathType Leaf) {
        try {
            $details = (& $candidate -c "import platform,sys; print(f'{sys.version_info.major}.{sys.version_info.minor}'); print(platform.architecture()[0])" 2>$null)
            if ($LASTEXITCODE -eq 0 -and $details.Count -ge 2 -and $details[0] -eq "3.12" -and $details[1] -eq "64bit") {
                return $candidate
            }
        }
        catch {
            return $null
        }
    }

    return $null
}

function Install-Python312 {
    $winget = Get-Command "winget.exe" -ErrorAction SilentlyContinue
    if ($null -eq $winget) {
        throw "Python 3.12 x64 is required, but winget.exe was not found. Install Python 3.12 x64, then run setup-windows.cmd again."
    }

    Write-Host "Installing CPython 3.12 x64 for this Windows user..."
    & $winget.Source install `
        --id Python.Python.3.12 `
        --exact `
        --source winget `
        --scope user `
        --accept-package-agreements `
        --accept-source-agreements `
        --disable-interactivity
    if ($LASTEXITCODE -ne 0) {
        throw "WinGet could not install Python 3.12 x64 (exit code $LASTEXITCODE)."
    }
}

$repo = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$bootstrap = Join-Path $repo "scripts\windows_setup.py"
if (-not (Test-Path $bootstrap -PathType Leaf)) {
    throw "XBrainLab bootstrap script was not found: $bootstrap"
}

$python = Get-Python312
if ($null -eq $python) {
    if ($PlanOnly) {
        [Console]::Error.WriteLine("Python 3.12 x64 is not installed. Run setup-windows.cmd without -PlanOnly to install it.")
        exit 2
    }
    Install-Python312
    $python = Get-Python312
}
if ($null -eq $python) {
    throw "Python 3.12 x64 was not available after installation. Open a new PowerShell window and run setup-windows.cmd again."
}

$arguments = @($bootstrap)
if ($Cpu) { $arguments += "--cpu" }
if ($Yes) { $arguments += "--yes" }
if ($NoLaunch) { $arguments += "--no-launch" }
if ($PlanOnly) { $arguments += "--plan-only" }

& $python -u @arguments
exit $LASTEXITCODE
