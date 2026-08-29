# Segment 4 — the platform components, split screen.
#
# Left:  terminal listing the fleet out of the platform Agent Registry, then
#        recalling this deal's entity memories out of Memory Bank.
# Right: the deployed dashboard Registry view, showing the same eight agents
#        with the versions, approval state and eval scores our own store adds.
#
# Staging mirrors record_beat6.ps1, which already handles the DPI scaling, the
# window seam and the crashed-profile problems.

param(
    [int]$Take = 1,
    [int]$Seconds = 30,
    [string]$Base = "https://diligence-room-dashboard-378831539922.asia-south1.run.app",
    [string]$Project = "diligence-room-live",
    [string]$Database = "diligence-asia",
    [switch]$StageOnly
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot/lib/windows.ps1"
Add-Type -AssemblyName System.Windows.Forms

$ffmpeg = Resolve-Ffmpeg
$ffprobe = Resolve-Ffmpeg -Name "ffprobe"

$repo = (Resolve-Path "$PSScriptRoot/../..").Path
$takes = Join-Path $repo "docs/video/takes"
New-Item -ItemType Directory -Force -Path $takes | Out-Null
$out = Join-Path $takes "platform_take$Take.mkv"

$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$halfW = [int]($bounds.Width / 2)
$fullH = $bounds.Height
$seam = 12

Move-Taskbar -Action park | Out-Null
Hide-ImeIndicators | Out-Null
Hide-SystemFlyouts | Out-Null

Close-IsolatedChrome
Start-Sleep 2

Start-IsolatedChrome -Url "$Base/registry" -X ($halfW - $seam) -Y 0 -W ($halfW + $seam) -H $fullH -Windowed

$startup = @(
    "`$env:GOOGLE_CLOUD_PROJECT='$Project'",
    "`$env:DILIGENCE_FIRESTORE_DATABASE='$Database'",
    "`$env:DILIGENCE_MEMORY_BANK_ENABLED='1'",
    "Set-Location '$repo'",
    # Warm the Vertex client during staging, before the camera rolls: the first
    # Memory Bank call pays a cold start that otherwise eats the take.
    "uv run python -W ignore scripts/video/recall_demo.py *> `$null",
    "Clear-Host"
) -join "; "
$consoleTitle = "PLATFORM-CONSOLE-$([guid]::NewGuid().ToString('N').Substring(0,6))"
$console = Start-StageConsole -Title $consoleTitle -StartupCommand $startup -NoExit

Start-Sleep 6
$chromeWin = $null
$deadline = (Get-Date).AddSeconds(25)
while ((Get-Date) -lt $deadline) {
    $chromeWin = Get-TopLevelWindows |
        Where-Object { $_.Title -like "*Diligence Room*" -and $_.Title -notlike "PLATFORM-CONSOLE*" } |
        Select-Object -First 1
    if ($chromeWin) { break }
    Start-Sleep -Milliseconds 400
}
if (-not $chromeWin) { throw "dashboard registry window never appeared" }
Set-WindowRect -Hwnd $chromeWin.Hwnd -X ($halfW - $seam) -Y 0 -W ($halfW + $seam) -H $fullH
Set-WindowTopmost -Hwnd $chromeWin.Hwnd
Write-Host "[platform] right: $($chromeWin.Title)"

Set-WindowRect -Hwnd $console.Hwnd -X 0 -Y 0 -W $halfW -H $fullH
Set-WindowTopmost -Hwnd $console.Hwnd
Start-Sleep 2

if ($StageOnly) {
    $shot = Join-Path $takes "_stage_platform.png"
    & $ffmpeg -hide_banner -loglevel error -y -f gdigrab -framerate 1 -draw_mouse 0 -i desktop -frames:v 1 $shot
    Write-Host "[platform] StageOnly frame -> $shot"
    Move-Taskbar -Action restore | Out-Null
    return
}

Write-Host "[platform] rolling $Seconds s -> $out"
$ff = Start-Process -FilePath $ffmpeg -PassThru -ArgumentList @(
    "-hide_banner", "-loglevel", "error", "-y",
    "-f", "gdigrab", "-framerate", "30", "-draw_mouse", "0", "-i", "desktop",
    "-t", "$Seconds",
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p",
    $out
)

Start-Sleep 2
Focus-WindowForInput -Hwnd $console.Hwnd | Out-Null
Start-Sleep 1
[System.Windows.Forms.SendKeys]::SendWait(".\scripts\video\platform_proof.ps1")
Start-Sleep 1
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")

$ff.WaitForExit()
$dur = & $ffprobe -v error -show_entries format=duration -of csv=p=0 $out
Write-Host "[platform] done duration=$dur"
Move-Taskbar -Action restore | Out-Null
