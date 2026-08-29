# Generic beat recorder: full-screen the deployed dashboard at one route and
# capture it. Used for every beat except beat 3 (which needs the split screen).
#
# Usage:
#   ...\record_view.ps1 -Beat 0 -Route "/findings" -Seconds 20
#   ...\record_view.ps1 -Beat 7 -Route "/findings/f4c993d48cda" -Seconds 25

param(
    [Parameter(Mandatory)][int]$Beat,
    [Parameter(Mandatory)][string]$Route,
    [Parameter(Mandatory)][int]$Seconds,
    [int]$Take = 1,
    [string]$Base = "https://diligence-room-dashboard-378831539922.asia-south1.run.app",
    [switch]$StageOnly,
    [switch]$Scroll,
    [int]$ScrollEvery = 6
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot/lib/windows.ps1"
Add-Type -AssemblyName System.Windows.Forms

$ffmpeg = Resolve-Ffmpeg
$ffprobe = Resolve-Ffmpeg -Name "ffprobe"

$repo = (Resolve-Path "$PSScriptRoot/../..").Path
$takes = Join-Path $repo "docs/video/takes"
New-Item -ItemType Directory -Force -Path $takes | Out-Null
$out = Join-Path $takes "beat${Beat}_take$Take.mkv"

$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$w = $bounds.Width
$h = $bounds.Height

Move-Taskbar -Action park | Out-Null
Hide-ImeIndicators | Out-Null
Hide-SystemFlyouts | Out-Null

# Close the previous beat's isolated window so its route does not win the
# title lookup below.
Close-IsolatedChrome
Start-Sleep 2

Start-IsolatedChrome -Url "$Base$Route" -X -8 -Y 0 -W ($w + 24) -H ($h + 8) -Windowed
Start-Sleep 6

$win = $null
$deadline = (Get-Date).AddSeconds(25)
while ((Get-Date) -lt $deadline) {
    $win = Get-TopLevelWindows |
        Where-Object { $_.Title -like "*Diligence Room*" -and $_.Title -notlike "REPLAY-CONSOLE*" } |
        Select-Object -First 1
    if ($win) { break }
    Start-Sleep -Milliseconds 400
}
if (-not $win) { throw "dashboard window never appeared for route $Route" }

Set-WindowRect -Hwnd $win.Hwnd -X -8 -Y 0 -W ($w + 24) -H ($h + 8)
Set-WindowTopmost -Hwnd $win.Hwnd
Start-Sleep 3

if ($StageOnly) {
    $shot = Join-Path $takes "_stage_beat$Beat.png"
    & $ffmpeg -hide_banner -loglevel error -y -f gdigrab -framerate 1 -draw_mouse 0 -i desktop -frames:v 1 $shot
    Write-Host "[beat$Beat] StageOnly frame -> $shot"
    Move-Taskbar -Action restore | Out-Null
    return
}

Write-Host "[beat$Beat] rolling $Seconds s ($Route) -> $out"
$ff = Start-Process -FilePath $ffmpeg -PassThru -ArgumentList @(
    "-hide_banner", "-loglevel", "error", "-y",
    "-f", "gdigrab", "-framerate", "30", "-draw_mouse", "0", "-i", "desktop",
    "-t", "$Seconds",
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p",
    $out
)

if ($Scroll) {
    # Walk down the page while the capture runs so long views read as a tour
    # rather than a screenshot. Pause first so the top of the page is on screen.
    Focus-WindowForInput -Hwnd $win.Hwnd | Out-Null
    Start-Sleep 4
    $elapsed = 4
    while ($elapsed -lt ($Seconds - 4)) {
        [System.Windows.Forms.SendKeys]::SendWait("{PGDN}")
        Start-Sleep $ScrollEvery
        $elapsed += $ScrollEvery
    }
}

$ff.WaitForExit()

$dur = & $ffprobe -v error -show_entries format=duration -of csv=p=0 $out
Write-Host "[beat$Beat] done duration=$dur"
Move-Taskbar -Action restore | Out-Null
