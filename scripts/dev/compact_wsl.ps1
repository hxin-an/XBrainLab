[CmdletBinding()]
param(
    [switch]$Apply
)

# Windows-only; run from a Windows path and never use WSL to find/compact its VHDX.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:TargetDistribution = 'Ubuntu-24.04'
$script:BackupRoot = 'E:\XBrainLabBackups'
$script:BackupSafetyBytes = 128MB

function Get-DriveSnapshot {
    param([Parameter(Mandatory)][ValidatePattern('^[A-Za-z]$')][string]$DriveLetter)

    $drive = Get-PSDrive -Name $DriveLetter -ErrorAction Stop
    [pscustomobject]@{ FreeBytes = [int64]$drive.Free; UsedBytes = [int64]$drive.Used }
}

function Test-IsAdministrator {
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [System.Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Assert-NoReparsePath {
    param(
        [Parameter(Mandatory)][string]$Path,
        [switch]$AllowMissingLeaf
    )

    $fullPath = [IO.Path]::GetFullPath($Path)
    $root = [IO.Path]::GetPathRoot($fullPath)
    if ([string]::IsNullOrWhiteSpace($root)) { throw "Path has no volume root: $Path" }
    $relative = $fullPath.Substring($root.Length).TrimStart('\')
    $current = $root
    foreach ($part in $relative.Split('\', [StringSplitOptions]::RemoveEmptyEntries)) {
        $current = Join-Path $current $part
        if (-not (Test-Path -LiteralPath $current)) {
            if ($AllowMissingLeaf -and $current -eq $fullPath) { return $fullPath }
            throw "Required path does not exist: $current"
        }
        $item = Get-Item -LiteralPath $current -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Reparse point is not permitted in this path: $current"
        }
    }
    return $fullPath
}

function Get-RunningWslDistributions {
    $wsl = Get-Command 'wsl.exe' -ErrorAction Stop
    $output = & $wsl.Source --list --running --quiet 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Unable to query running WSL distributions: $output" }
    return @($output | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

function Assert-AllWslStopped {
    $running = @(Get-RunningWslDistributions)
    if ($running.Count -ne 0) {
        throw "All WSL distributions must be stopped before Apply. Running: $($running -join ', ')"
    }
}

function Resolve-TargetVhd {
    $lxss = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss'
    if (-not (Test-Path -LiteralPath $lxss)) { throw 'WSL registration was not found for the current Windows user.' }
    $matches = @(Get-ChildItem -LiteralPath $lxss | ForEach-Object {
        $properties = Get-ItemProperty -LiteralPath $_.PSPath
        if ($properties.DistributionName -eq $script:TargetDistribution) {
            [pscustomobject]@{ Key = $_.PSChildName; BasePath = [string]$properties.BasePath }
        }
    })
    if ($matches.Count -ne 1) {
        throw "Expected exactly one registered $script:TargetDistribution distribution; found $($matches.Count)."
    }
    $basePath = Assert-NoReparsePath -Path $matches[0].BasePath
    $vhdPath = Assert-NoReparsePath -Path (Join-Path $basePath 'ext4.vhdx')
    $vhd = Get-Item -LiteralPath $vhdPath -Force
    if ($vhd.PSIsContainer) { throw "WSL VHDX is not a file: $vhdPath" }
    [pscustomobject]@{
        Key = $matches[0].Key; BasePath = $basePath; VhdPath = $vhdPath
        Length = [int64]$vhd.Length; LastWriteUtc = $vhd.LastWriteTimeUtc
    }
}

function Assert-SameTarget {
    param([Parameter(Mandatory)]$Expected, [Parameter(Mandatory)]$Actual)
    if ($Expected.Key -ne $Actual.Key -or $Expected.VhdPath -ne $Actual.VhdPath) {
        throw 'WSL registration or VHDX identity changed during this operation.'
    }
}

function Open-ExclusiveVhd {
    param([Parameter(Mandatory)][string]$VhdPath)
    try {
        return [IO.File]::Open($VhdPath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::None)
    } catch {
        throw "The registered VHDX is in use and cannot be opened exclusively: $VhdPath. $($_.Exception.Message)"
    }
}

function Open-VhdReadLock {
    param([Parameter(Mandatory)][string]$VhdPath)
    try {
        return [IO.File]::Open($VhdPath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    } catch {
        throw "The registered VHDX cannot be read-locked: $VhdPath. $($_.Exception.Message)"
    }
}

function Get-FileSha256 {
    param([Parameter(Mandatory)][string]$Path)
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path -ErrorAction Stop).Hash
}

function Get-Sha256FromStream {
    param([Parameter(Mandatory)][IO.Stream]$Stream)
    $Stream.Position = 0
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha256.ComputeHash($Stream))).Replace('-', '')
    } finally {
        $sha256.Dispose()
    }
}

function New-ProtectedRunDirectory {
    param([Parameter(Mandatory)][string]$BackupRoot)

    $volume = Split-Path -Qualifier $BackupRoot
    if ([string]::IsNullOrWhiteSpace($volume)) { throw "Backup root must be an absolute Windows path: $BackupRoot" }
    $drive = Get-Volume -DriveLetter $volume.TrimEnd(':') -ErrorAction Stop
    if ($drive.FileSystem -ne 'NTFS') { throw "Backup volume must be NTFS for access control enforcement: $volume" }
    if (-not (Test-Path -LiteralPath $BackupRoot)) {
        $parent = Split-Path -Parent $BackupRoot
        Assert-NoReparsePath -Path $parent | Out-Null
        New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
    }
    $safeRoot = Assert-NoReparsePath -Path $BackupRoot
    $runDirectory = Join-Path $safeRoot ('XBrainLab-WslCompaction-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $runDirectory -ErrorAction Stop | Out-Null
    $currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    & icacls.exe $runDirectory '/inheritance:r' "/grant:r" "${currentUser}:(OI)(CI)F" '*S-1-5-32-544:(OI)(CI)F' 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to set private NTFS permissions on $runDirectory" }
    return (Assert-NoReparsePath -Path $runDirectory)
}

function Assert-BackupCapacity {
    param([Parameter(Mandatory)][string]$BackupRoot, [Parameter(Mandatory)][int64]$SourceLength)
    $qualifier = Split-Path -Qualifier $BackupRoot
    $snapshot = Get-DriveSnapshot -DriveLetter $qualifier.TrimEnd(':')
    $required = $SourceLength + $script:BackupSafetyBytes
    if ($snapshot.FreeBytes -lt $required) {
        throw "Backup volume has insufficient free space. Required: $required bytes; available: $($snapshot.FreeBytes) bytes."
    }
}

function Copy-VhdFile {
    param([Parameter(Mandatory)][string]$Source, [Parameter(Mandatory)][string]$Destination)
    Copy-Item -LiteralPath $Source -Destination $Destination -ErrorAction Stop
}

function Copy-VerifiedVhd {
    param(
        [Parameter(Mandatory)][string]$Source,
        [Parameter(Mandatory)][IO.Stream]$SourceLock,
        [Parameter(Mandatory)][string]$RunDirectory
    )
    $destination = Join-Path $RunDirectory 'Ubuntu-24.04-ext4.vhdx.bak'
    if (Test-Path -LiteralPath $destination) { throw "Refusing to overwrite existing backup: $destination" }
    $sourceBefore = Get-Sha256FromStream -Stream $SourceLock
    Copy-VhdFile -Source $Source -Destination $destination
    $backupHash = Get-FileSha256 -Path $destination
    $sourceAfter = Get-Sha256FromStream -Stream $SourceLock
    if ($sourceBefore -ne $backupHash -or $sourceAfter -ne $backupHash) {
        throw 'Backup hash verification failed; DiskPart will not run.'
    }
    [pscustomobject]@{ Path = $destination; Sha256 = $backupHash }
}

function Invoke-DiskPartNative {
    param([Parameter(Mandatory)][string]$InputPath)
    $output = & diskpart.exe /s $InputPath 2>&1 | Out-String
    [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = $output }
}

function Get-DiskPartSuccessMarker {
    param(
        [Parameter(Mandatory)][ValidateSet('attach', 'detach', 'compact')][string]$Operation,
        [Parameter(Mandatory)][ValidateSet('English', 'TraditionalChinese')][string]$Language
    )
    if ($Language -eq 'English') {
        return @{ attach = 'DiskPart successfully attached the virtual disk file.'; detach = 'DiskPart successfully detached the virtual disk file.'; compact = 'DiskPart successfully compacted the virtual disk file.' }[$Operation]
    }
    # Keep this .ps1 ASCII-only so Windows PowerShell 5.1 parses it correctly
    # when launched from a UTF-8 UNC share without a BOM.
    $bytes = @{
        attach = [byte[]](68,105,115,107,80,97,114,116,32,229,183,178,230,136,144,229,138,159,233,153,132,229,138,160,232,153,155,230,147,172,231,163,129,231,162,159,230,170,148,230,161,136,227,128,130)
        detach = [byte[]](68,105,115,107,80,97,114,116,32,229,183,178,230,136,144,229,138,159,228,184,173,230,150,183,233,128,163,231,181,144,232,153,155,230,147,172,231,163,129,231,162,159,230,170,148,230,161,136,227,128,130)
        compact = [byte[]](68,105,115,107,80,97,114,116,32,229,183,178,230,136,144,229,138,159,229,163,147,231,184,174,232,153,155,230,147,172,231,163,129,231,162,159,230,170,148,230,161,136,227,128,130)
    }
    return [System.Text.Encoding]::UTF8.GetString($bytes[$Operation])
}

function Test-DiskPartSuccess {
    param([Parameter(Mandatory)][ValidateSet('attach', 'detach', 'compact')][string]$Operation, [Parameter(Mandatory)][string]$Output)
    return $Output.Contains((Get-DiskPartSuccessMarker -Operation $Operation -Language English)) -or $Output.Contains((Get-DiskPartSuccessMarker -Operation $Operation -Language TraditionalChinese))
}

function Test-DiskPartFailure {
    param([Parameter(Mandatory)][string]$Output)
    $traditionalError = [System.Text.Encoding]::UTF8.GetString([byte[]](233,140,175,232,170,164))
    return $Output -match '(?im)DiskPart has encountered an error|^\s*error\s*:' -or $Output.Contains($traditionalError)
}

function Invoke-DiskPartLine {
    param(
        [Parameter(Mandatory)][string[]]$Lines,
        [Parameter(Mandatory)][string]$RunDirectory,
        [Parameter(Mandatory)][ValidateSet('attach', 'detach', 'compact')][string]$Name
    )
    $input = Join-Path $RunDirectory "$Name.txt"
    [IO.File]::WriteAllLines($input, [string[]]$Lines, [System.Text.UTF8Encoding]::new($false))
    $native = Invoke-DiskPartNative -InputPath $input
    $result = [string]$native.Output
    [IO.File]::WriteAllText(
        (Join-Path $RunDirectory "$Name-output.log"),
        $result,
        [System.Text.UTF8Encoding]::new($false)
    )
    if ($native.ExitCode -ne 0 -or (Test-DiskPartFailure -Output $result) -or -not (Test-DiskPartSuccess -Operation $Name -Output $result)) {
        throw "DiskPart $Name failed: $result"
    }
    return $result
}

function Attach-ReadonlyVhd {
    param([Parameter(Mandatory)][string]$VhdPath, [Parameter(Mandatory)][string]$RunDirectory)
    $escaped = $VhdPath.Replace('"', '""')
    $attachAttempted = $false
    $attached = $false
    try {
        $attachAttempted = $true
        Invoke-DiskPartLine -Lines @(('select vdisk file="{0}"' -f $escaped), 'attach vdisk readonly') -RunDirectory $RunDirectory -Name 'attach' | Out-Null
        $attached = $true
        return $true
    } finally {
        if ($attachAttempted -and -not $attached) {
            Invoke-DiskPartLine -Lines @(('select vdisk file="{0}"' -f $escaped), 'detach vdisk') -RunDirectory $RunDirectory -Name 'detach' | Out-Null
        }
    }
}

function Detach-Vhd {
    param([Parameter(Mandatory)][string]$VhdPath, [Parameter(Mandatory)][string]$RunDirectory)
    $escaped = $VhdPath.Replace('"', '""')
    Invoke-DiskPartLine -Lines @(('select vdisk file="{0}"' -f $escaped), 'detach vdisk') -RunDirectory $RunDirectory -Name 'detach' | Out-Null
}

function Compact-ReadonlyAttachedVhd {
    param([Parameter(Mandatory)][string]$VhdPath, [Parameter(Mandatory)][string]$RunDirectory)
    $escaped = $VhdPath.Replace('"', '""')
    Invoke-DiskPartLine -Lines @(('select vdisk file="{0}"' -f $escaped), 'compact vdisk') -RunDirectory $RunDirectory -Name 'compact' | Out-Null
}

function Start-TargetPostcheck {
    $wsl = Get-Command 'wsl.exe' -ErrorAction Stop
    $output = & $wsl.Source -d $script:TargetDistribution --exec /bin/sh -c 'printf xbrainlab-wsl-compact-ok' 2>&1
    if ($LASTEXITCODE -ne 0 -or "$output" -notmatch 'xbrainlab-wsl-compact-ok') {
        throw "Post-compaction WSL check failed: $output"
    }
}

function Show-Preview {
    $target = Resolve-TargetVhd
    $sourceDrive = Split-Path -Qualifier $target.VhdPath
    $source = Get-DriveSnapshot -DriveLetter $sourceDrive.TrimEnd(':')
    [pscustomobject]@{
        Mode = 'Preview'; Distribution = $script:TargetDistribution; VhdPath = $target.VhdPath
        VhdBytes = $target.Length; SourceFreeBytes = $source.FreeBytes; BackupRoot = $script:BackupRoot
        Notes = 'No WSL state, VHDX, backup, or DiskPart operation was changed.'
    }
}

function Invoke-Compaction {
    param([Parameter(Mandatory)][string]$BackupRoot)

    if (-not (Test-IsAdministrator)) { throw 'Apply requires an elevated Administrator PowerShell session.' }
    $target = Resolve-TargetVhd
    $sourceDrive = (Split-Path -Qualifier $target.VhdPath).TrimEnd(':')
    $before = Get-DriveSnapshot -DriveLetter $sourceDrive
    Assert-AllWslStopped
    $exclusive = Open-ExclusiveVhd -VhdPath $target.VhdPath
    $readLock = $null
    $readonlyAttached = $false
    $runDirectory = $null
    try {
        # Rule out a writer, then retain a read-share lock for backup and hashes.
        $exclusive.Dispose(); $exclusive = $null
        $readLock = Open-VhdReadLock -VhdPath $target.VhdPath
        $runDirectory = New-ProtectedRunDirectory -BackupRoot $BackupRoot
        Assert-BackupCapacity -BackupRoot $BackupRoot -SourceLength $target.Length
        $backup = Copy-VerifiedVhd -Source $target.VhdPath -SourceLock $readLock -RunDirectory $runDirectory
        Assert-AllWslStopped
        $again = Resolve-TargetVhd
        Assert-SameTarget -Expected $target -Actual $again
        # The pre-attach hash runs while the source is still write-blocked.
        if ((Get-Sha256FromStream -Stream $readLock) -ne $backup.Sha256) {
            throw 'Source changed after backup verification; DiskPart will not run.'
        }
        Attach-ReadonlyVhd -VhdPath $again.VhdPath -RunDirectory $runDirectory | Out-Null
        $readonlyAttached = $true
        # Recheck after DiskPart attached it readonly, before its writable compact step.
        if ((Get-Sha256FromStream -Stream $readLock) -ne $backup.Sha256) {
            throw 'Source changed after readonly attachment; DiskPart will not run.'
        }
        $readLock.Dispose(); $readLock = $null
        Compact-ReadonlyAttachedVhd -VhdPath $again.VhdPath -RunDirectory $runDirectory
        Detach-Vhd -VhdPath $again.VhdPath -RunDirectory $runDirectory
        $readonlyAttached = $false
        $afterVhd = (Get-Item -LiteralPath $again.VhdPath -Force).Length
        $after = Get-DriveSnapshot -DriveLetter $sourceDrive
        Start-TargetPostcheck
        [pscustomobject]@{
            Mode = 'Applied'; Distribution = $script:TargetDistribution; VhdPath = $again.VhdPath
            VhdBytesBefore = $target.Length; VhdBytesAfter = [int64]$afterVhd
            SourceFreeBytesBefore = $before.FreeBytes; SourceFreeBytesAfter = $after.FreeBytes
            BackupPath = $backup.Path; BackupSha256 = $backup.Sha256; LogDirectory = $runDirectory
        }
    } finally {
        if ($null -ne $readLock) { $readLock.Dispose() }
        if ($readonlyAttached) {
            # A detach failure is intentionally fatal and suppresses postcheck.
            Detach-Vhd -VhdPath $target.VhdPath -RunDirectory $runDirectory
        }
        if ($null -ne $exclusive) { $exclusive.Dispose() }
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    try {
        if ($Apply) { Invoke-Compaction -BackupRoot $script:BackupRoot | Format-List }
        else { Show-Preview | Format-List }
    } catch {
        Write-Error $_.Exception.Message
        exit 1
    }
}
