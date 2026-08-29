# Beat 7 — deployment proof, entirely inside the Google Cloud Console.
#
# Left:  Cloud Run request logs for the deployed dashboard. The approval POST
#        recorded just before the take appears here, so the human-in-the-loop
#        gate is proven by a cloud log rather than a local terminal.
# Right: Cloud Trace, showing the spans the fleet emits.
#
# No on-device terminal: the rules ask for Google Cloud Console / Cloud Run
# dashboard / Vertex AI logs, and a local shell proves none of those.

param(
    [int]$Take = 3,
    [int]$Seconds = 30,
    # /run/detail/<region>/<service>/logs is a dead path in the current console
    # ("URL not found"); Logs Explorer takes a pinned query and is stable.
    [string]$LogsUrl = "https://console.cloud.google.com/logs/query;query=resource.type%3D%22cloud_run_revision%22?project=diligence-room-live",
    [string]$TraceUrl = "https://console.cloud.google.com/traces/list?project=diligence-room-live",
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
$out = Join-Path $takes "beat7_take$Take.mkv"

$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$halfW = [int]($bounds.Width / 2)
$fullH = $bounds.Height
$seam = 12

Move-Taskbar -Action park | Out-Null
Hide-ImeIndicators | Out-Null
Hide-SystemFlyouts | Out-Null

Close-IsolatedChrome
Start-Sleep 2

Start-IsolatedChrome -Url $LogsUrl -X -8 -Y 0 -W ($halfW + $seam) -H $fullH -Windowed
Start-Sleep 8
Start-IsolatedChrome -Url $TraceUrl -X ($halfW - $seam) -Y 0 -W ($halfW + 44) -H $fullH -Windowed

# The Console is heavy; both tabs need time to authenticate and paint.
Start-Sleep 16

function Find-ConsoleWindow {
    param([string[]]$Match)
    foreach ($m in $Match) {
        $w = Get-TopLevelWindows | Where-Object { $_.Title -like "*$m*" } | Select-Object -First 1
        if ($w) { return $w }
    }
    return $null
}

$logsWin = Find-ConsoleWindow -Match @("Logs Explorer", "Logging")
$traceWin = Find-ConsoleWindow -Match @("Trace")
if (-not $logsWin) { throw "Cloud Run logs window not found" }
if (-not $traceWin) { throw "Cloud Trace window not found" }
if ($logsWin.Hwnd -eq $traceWin.Hwnd) { throw "both panes resolved to the same window" }

Set-WindowRect -Hwnd $logsWin.Hwnd -X -8 -Y 0 -W ($halfW + $seam) -H $fullH
Set-WindowTopmost -Hwnd $logsWin.Hwnd
Set-WindowRect -Hwnd $traceWin.Hwnd -X ($halfW - $seam) -Y 0 -W ($halfW + 44) -H $fullH
Set-WindowTopmost -Hwnd $traceWin.Hwnd
Write-Host "[beat7] left : $($logsWin.Title)"
Write-Host "[beat7] right: $($traceWin.Title)"
Start-Sleep 3

if ($StageOnly) {
    $shot = Join-Path $takes "_stage_beat7.png"
    & $ffmpeg -hide_banner -loglevel error -y -f gdigrab -framerate 1 -draw_mouse 0 -i desktop -frames:v 1 $shot
    Write-Host "[beat7] StageOnly frame -> $shot"
    Move-Taskbar -Action restore | Out-Null
    return
}

Write-Host "[beat7] rolling $Seconds s -> $out"
& $ffmpeg -hide_banner -loglevel error -y `
    -f gdigrab -framerate 30 -draw_mouse 0 -i desktop `
    -t $Seconds `
    -c:v libx264 -preset veryfast -crf 16 -pix_fmt yuv420p `
    $out

$dur = & $ffprobe -v error -show_entries format=duration -of csv=p=0 $out
Write-Host "[beat7] done duration=$dur"
Move-Taskbar -Action restore | Out-Null
