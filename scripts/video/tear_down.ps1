# Session tear-down: kills the bring-up process trees (emulator + dashboard shell).
# Usage: scripts/video/tear_down.ps1

$ErrorActionPreference = "Stop"
$repo = Resolve-Path "$PSScriptRoot/../.."
$statePath = Join-Path $repo "docs/video/takes/session-state.json"

if (-not (Test-Path $statePath)) {
    Write-Host "[tear-down] no session state; nothing to do"
    exit 0
}
$state = Get-Content $statePath -Raw | ConvertFrom-Json
foreach ($key in @("shell_pid", "emulator_pid")) {
    $pid2 = $state.$key
    if ($pid2) {
        & taskkill /PID $pid2 /T /F 2>&1 | Out-Null
        Write-Host "[tear-down] killed $key ($pid2)"
    }
}
Remove-Item $statePath
Write-Host "[tear-down] done"
