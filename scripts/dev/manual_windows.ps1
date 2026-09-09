[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{40}$')][string]$Sha,
    [ValidateSet('prepare', 'check', 'launch', 'clean')][string]$Action = 'launch',
    [string]$Source = 'D:\workspace_v2\projects\lab\xbrainlab-manual',
    [string]$Python = 'D:\workspace_v2\projects\lab\XBrainLab\.venv\Scripts\python.exe',
    [string]$Cache = 'D:\XBrainLabCache',
    [switch]$Apply,
    [switch]$Accepted
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Shared Windows Python is missing: $Python. No installation was attempted."
}
$entrypoint = Join-Path $PSScriptRoot 'manual_environment.py'
$arguments = @($entrypoint, $Action, '--source', $Source, '--sha', $Sha, '--cache', $Cache)
if ($Apply) { $arguments += '--apply' }
if ($Accepted) { $arguments += '--accepted' }
# Synchronous execution keeps the Python lifetime/lease and live log in this console.
& $Python @arguments
exit $LASTEXITCODE
