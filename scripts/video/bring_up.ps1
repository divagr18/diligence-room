# Session bring-up for recording: Firestore emulator + a single dashboard shell
# (dashboard.main:app serves the static SPA AND the emulator-backed API on :8040).
# Usage: scripts/video/bring_up.ps1  (state -> docs/video/takes/session-state.json)

param([int]$EmulatorPort = 8080, [int]$ShellPort = 8040)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot/lib/windows.ps1"

$repo = Resolve-Path "$PSScriptRoot/../.."
$takes = Join-Path $repo "docs/video/takes"
New-Item -ItemType Directory -Force -Path $takes | Out-Null
$statePath = Join-Path $takes "session-state.json"

function Start-TrackedConsole {
    param([string]$Title, [string]$Command)
    $body = "`$Host.UI.RawUI.WindowTitle = '$Title'"
    if ($Command) { $body += "; $Command" }
    $proc = Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoLogo", "-NoProfile", "-NoExit", "-Command", $body) -PassThru
    $deadline = (Get-Date).AddSeconds(20)
    $win = $null
    while ((Get-Date) -lt $deadline) {
        $win = Find-WindowByTitle -Like $Title
        if ($win) { break }
        Start-Sleep -Milliseconds 300
    }
    if (-not $win) { throw "console '$Title' did not appear" }
    Set-WindowRect -Hwnd $win.Hwnd -X -2400 -Y 0 -W 900 -H 600
    return [pscustomobject]@{ Title = $Title; Pid = $proc.Id; Hwnd = $win.Hwnd }
}

function Wait-Http {
    param([string]$Url, [int]$TimeoutSeconds = 90)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -eq 200) { return $r.Content }
        } catch { Start-Sleep -Milliseconds 700 }
    }
    throw "health gate failed: $Url"
}

Write-Host "[bring-up] emulator on 127.0.0.1:$EmulatorPort"
$emu = Start-TrackedConsole -Title "VIDEO-EMU" -Command "gcloud beta emulators firestore start --host-port=127.0.0.1:$EmulatorPort --quiet"
$ready = $false
$deadline = (Get-Date).AddSeconds(90)
while ((Get-Date) -lt $deadline) {
    try {
        $c = New-Object System.Net.Sockets.TcpClient("127.0.0.1", $EmulatorPort)
        $c.Close(); $ready = $true; break
    } catch { Start-Sleep -Milliseconds 700 }
}
if (-not $ready) { throw "emulator not ready in 90s" }
Write-Host "[bring-up] emulator ready"

Write-Host "[bring-up] dashboard shell (SPA + emulator-backed API) on :$ShellPort"
$shell = Start-TrackedConsole -Title "VIDEO-SHELL" -Command "Set-Location '$repo'; `$env:FIRESTORE_EMULATOR_HOST='127.0.0.1:$EmulatorPort'; `$env:GOOGLE_CLOUD_PROJECT='diligence-room'; uv run uvicorn dashboard.main:app --port $ShellPort"
$health = Wait-Http "http://127.0.0.1:$ShellPort/api/health"
Write-Host "[bring-up] shell API health: $health"
$root = Wait-Http "http://127.0.0.1:$ShellPort/"
if ($root -notmatch "<html") { throw "shell SPA did not serve index.html" }
Write-Host "[bring-up] shell SPA serves index.html"

$state = @{
    emulator_port = $EmulatorPort
    shell_port = $ShellPort
    emulator_pid = $emu.Pid
    shell_pid = $shell.Pid
    brought_up_at = (Get-Date).ToUniversalTime().ToString("o")
}
$state | ConvertTo-Json | Set-Content $statePath
Write-Host "[bring-up] GREEN - state at $statePath"
