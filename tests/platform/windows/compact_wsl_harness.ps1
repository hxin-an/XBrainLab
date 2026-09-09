[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('Preview', 'BackupFailure', 'Apply', 'ActiveWsl', 'ExistingBackup', 'SourceChanged', 'DiskPartOutput', 'DetachFailure', 'CompactFailure')][string]$Scenario,
    [Parameter(Mandatory)][string]$ScriptPath,
    [Parameter(Mandatory)][string]$TempRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. $ScriptPath

if (Test-Path -LiteralPath $TempRoot) { throw 'Harness requires a new disposable directory; refusing an existing target.' }
if ((Split-Path -Leaf $TempRoot) -ne $Scenario) { throw 'Harness target must be named for its scenario.' }
New-Item -ItemType Directory -Path $TempRoot | Out-Null
$vhd = Join-Path $TempRoot 'ext4.vhdx'
[IO.File]::WriteAllBytes($vhd, [byte[]](1..64))
$script:events = [Collections.Generic.List[string]]::new()
$script:target = [pscustomobject]@{ Key = 'test'; BasePath = $TempRoot; VhdPath = $vhd; Length = [int64](Get-Item $vhd).Length; LastWriteUtc = [DateTime]::UtcNow }

function Resolve-TargetVhd { $script:target }
function Get-DriveSnapshot { param([string]$DriveLetter) [pscustomobject]@{ FreeBytes = [int64]999999999; UsedBytes = [int64]1 } }
function Test-IsAdministrator { $true }
function Get-RunningWslDistributions { @() }
function Start-TargetPostcheck { $script:events.Add('postcheck') }
function Attach-ReadonlyVhd {
    param([string]$VhdPath, [string]$RunDirectory)
    $script:events.Add('attach')
}
function Detach-Vhd {
    param([string]$VhdPath, [string]$RunDirectory)
    $script:events.Add('detach')
}
function Compact-ReadonlyAttachedVhd {
    param([string]$VhdPath, [string]$RunDirectory)
    if (-not (Test-Path -LiteralPath (Join-Path $RunDirectory 'Ubuntu-24.04-ext4.vhdx.bak'))) { throw 'backup missing before compact' }
    $script:events.Add('compact')
}

try {
    if ($Scenario -eq 'Preview') {
        $result = Show-Preview
        $passed = $result.Mode -eq 'Preview' -and $script:events.Count -eq 0 -and -not (Test-Path (Join-Path $TempRoot 'XBrainLab-WslCompaction-test'))
    } elseif ($Scenario -eq 'BackupFailure') {
        function Copy-VerifiedVhd { throw 'intentional backup failure' }
        try { Invoke-Compaction -BackupRoot $TempRoot | Out-Null; $passed = $false } catch { $passed = $_.Exception.Message -match 'intentional backup failure' -and $script:events.Count -eq 0 }
    } elseif ($Scenario -eq 'ActiveWsl') {
        function Get-RunningWslDistributions { @('Ubuntu-24.04') }
        try { Assert-AllWslStopped; $passed = $false } catch { $passed = $_.Exception.Message -match 'must be stopped' }
    } elseif ($Scenario -eq 'ExistingBackup') {
        $runDirectory = Join-Path $TempRoot 'existing'
        New-Item -ItemType Directory -Path $runDirectory | Out-Null
        $backup = Join-Path $runDirectory 'Ubuntu-24.04-ext4.vhdx.bak'
        [IO.File]::WriteAllBytes($backup, [byte[]](9, 9, 9))
        $lock = Open-VhdReadLock -VhdPath $vhd
        try { Copy-VerifiedVhd -Source $vhd -SourceLock $lock -RunDirectory $runDirectory | Out-Null; $passed = $false } catch { $passed = $_.Exception.Message -match 'Refusing to overwrite' -and ([IO.File]::ReadAllBytes($backup).Length -eq 3) } finally { $lock.Dispose() }
    } elseif ($Scenario -eq 'SourceChanged') {
        $runDirectory = Join-Path $TempRoot 'changed'
        New-Item -ItemType Directory -Path $runDirectory | Out-Null
        $staleLock = [IO.MemoryStream]::new([IO.File]::ReadAllBytes($vhd))
        function Copy-VhdFile {
            param([string]$Source, [string]$Destination)
            [IO.File]::WriteAllBytes($Source, [byte[]](65..128))
            Microsoft.PowerShell.Management\Copy-Item -LiteralPath $Source -Destination $Destination -ErrorAction Stop
        }
        try { Copy-VerifiedVhd -Source $vhd -SourceLock $staleLock -RunDirectory $runDirectory | Out-Null; $passed = $false } catch { $passed = $_.Exception.Message -match 'hash verification failed' } finally { $staleLock.Dispose() }
    } elseif ($Scenario -eq 'DiskPartOutput') {
        $runDirectory = Join-Path $TempRoot 'diskpart'
        New-Item -ItemType Directory -Path $runDirectory | Out-Null
        # Captured verbatim from Windows 11 zh-TW DiskPart attach output, encoded
        # as bytes to keep this Windows PowerShell 5.1 source ASCII-only.
        $script:diskpartOutput = [System.Text.Encoding]::UTF8.GetString([byte[]](68,105,115,107,80,97,114,116,32,229,183,178,230,136,144,229,138,159,233,128,163,231,181,144,232,153,155,230,147,172,231,163,129,231,162,159,230,170,148,230,161,136,227,128,130))
        function Invoke-DiskPartNative { param([string]$InputPath) [pscustomobject]@{ ExitCode = 0; Output = $script:diskpartOutput } }
        Invoke-DiskPartLine -Lines @('select vdisk file="x"', 'attach vdisk readonly') -RunDirectory $runDirectory -Name 'attach' | Out-Null
        $script:diskpartOutput = (Get-DiskPartSuccessMarker -Operation compact -Language English) + "`nDiskPart has encountered an error: access denied."
        try { Invoke-DiskPartLine -Lines @('select vdisk file="x"', 'compact vdisk') -RunDirectory $runDirectory -Name 'compact' | Out-Null; $passed = $false } catch { $passed = $_.Exception.Message -match 'DiskPart compact failed' -and (Get-Content -LiteralPath (Join-Path $runDirectory 'compact-output.log') -Raw) -match 'encountered an error' }
    } elseif ($Scenario -eq 'DetachFailure') {
        function Detach-Vhd { throw 'intentional detach failure' }
        try { Invoke-Compaction -BackupRoot $TempRoot | Out-Null; $passed = $false } catch { $passed = $_.Exception.Message -match 'intentional detach failure' -and ($script:events -join ',') -eq 'attach,compact' }
    } elseif ($Scenario -eq 'CompactFailure') {
        function Compact-ReadonlyAttachedVhd { throw 'intentional compact failure' }
        try { Invoke-Compaction -BackupRoot $TempRoot | Out-Null; $passed = $false } catch { $passed = $_.Exception.Message -match 'intentional compact failure' -and ($script:events -join ',') -eq 'attach,detach' }
    } else {
        $result = Invoke-Compaction -BackupRoot $TempRoot
        $protected = (Get-Acl -LiteralPath $result.LogDirectory).AreAccessRulesProtected
        $passed = $result.Mode -eq 'Applied' -and ($script:events -join ',') -eq 'attach,compact,detach,postcheck' -and $protected -and (Test-Path -LiteralPath $result.BackupPath) -and $result.BackupSha256 -eq (Get-FileHash -LiteralPath $result.BackupPath -Algorithm SHA256).Hash
    }
    [pscustomobject]@{ passed = [bool]$passed; scenario = $Scenario; events = @($script:events) } | ConvertTo-Json -Compress
    if (-not $passed) { exit 1 }
} finally {
    Remove-Item -LiteralPath $TempRoot -Force -Recurse -ErrorAction SilentlyContinue
}
