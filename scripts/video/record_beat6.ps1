# Beat 6 — upgrade, failed eval, rollback, shown happening.
# Console left runs the rollback script; Registry view right is refreshed at the
# two moments the serving version changes, so v2.4 -> v2.5 -> v2.4 is visible.

param(
    [int]$Take = 1,
    [int]$Seconds = 29,
    [string]$Base = "https://diligence-room-dashboard-378831539922.asia-south1.run.app",
    [string]$Project = "diligence-room-live",
    [string]$Database = "diligence-asia",
    [double]$Pace = 1.4,
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
$out = Join-Path $takes "beat6_take$Take.mkv"

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
    "Set-Location '$repo'",
    "Clear-Host"
) -join "; "
$consoleTitle = "ROLLBACK-CONSOLE-$([guid]::NewGuid().ToString('N').Substring(0,6))"
$console = Start-StageConsole -Title $consoleTitle -StartupCommand $startup -NoExit

Start-Sleep 6
$chromeWin = $null
$deadline = (Get-Date).AddSeconds(25)
while ((Get-Date) -lt $deadline) {
    $chromeWin = Get-TopLevelWindows |
        Where-Object { $_.Title -like "*Diligence Room*" -and $_.Title -notlike "ROLLBACK-CONSOLE*" } |
        Select-Object -First 1
    if ($chromeWin) { break }
    Start-Sleep -Milliseconds 400
}
if (-not $chromeWin) { throw "registry window never appeared" }
Set-WindowRect -Hwnd $chromeWin.Hwnd -X ($halfW - $seam) -Y 0 -W ($halfW + $seam) -H $fullH
Set-WindowTopmost -Hwnd $chromeWin.Hwnd

Set-WindowRect -Hwnd $console.Hwnd -X 0 -Y 0 -W $halfW -H $fullH
Set-WindowTopmost -Hwnd $console.Hwnd
Start-Sleep 2

if ($StageOnly) {
    $shot = Join-Path $takes "_stage_beat6.png"
    & $ffmpeg -hide_banner -loglevel error -y -f gdigrab -framerate 1 -draw_mouse 0 -i desktop -frames:v 1 $shot
    Write-Host "[beat6] StageOnly frame -> $shot"
    Move-Taskbar -Action restore | Out-Null
    return
}

Write-Host "[beat6] rolling $Seconds s -> $out"
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
[System.Windows.Forms.SendKeys]::SendWait("uv run python scripts/video/beat6_rollback.py --pace $Pace")
Start-Sleep 1
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")

# Refresh the Registry twice: once while v2.5 is serving, once after rollback.
# The Registry view does not poll (only Findings does), so the reload is what
# makes the version change visible.
Start-Sleep 9
Focus-WindowForInput -Hwnd $chromeWin.Hwnd | Out-Null
[System.Windows.Forms.SendKeys]::SendWait("{F5}")
Start-Sleep 13
Focus-WindowForInput -Hwnd $chromeWin.Hwnd | Out-Null
[System.Windows.Forms.SendKeys]::SendWait("{F5}")

$ff.WaitForExit()
$dur = & $ffprobe -v error -show_entries format=duration -of csv=p=0 $out
Write-Host "[beat6] done duration=$dur"
Move-Taskbar -Action restore | Out-Null
