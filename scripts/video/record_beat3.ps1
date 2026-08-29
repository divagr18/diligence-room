# Beat 3 — the one unbroken take: terminal left, deployed dashboard right,
# live replay writing to live Firestore while the dashboard polls it.
#
#   -StageOnly   stage the windows and grab one frame; run nothing
#   (default)    stage, roll ffmpeg, then type the replay command on camera
#
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\video\record_beat3.ps1 -Take 1

param(
    [int]$Take = 1,
    [int]$Seconds = 65,
    [string]$Dashboard = "https://diligence-room-dashboard-378831539922.asia-south1.run.app/findings",
    [string]$Project = "diligence-room-live",
    [string]$Database = "diligence-asia",
    [int]$Speed = 60000,
    [switch]$StageOnly,
    # Beats 2 and 3 come from one continuous take, so the file name is explicit.
    [string]$OutName = ""
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot/lib/windows.ps1"
Add-Type -AssemblyName System.Windows.Forms

$ffmpeg = Resolve-Ffmpeg
$ffprobe = Resolve-Ffmpeg -Name "ffprobe"

$repo = (Resolve-Path "$PSScriptRoot/../..").Path
$takes = Join-Path $repo "docs/video/takes"
New-Item -ItemType Directory -Force -Path $takes | Out-Null
$out = if ($OutName) { Join-Path $takes $OutName } else { Join-Path $takes "beat3_take$Take.mkv" }

# SetWindowPos takes coordinates in this process's (DPI-unaware) space, while
# gdigrab captures physical pixels. On a scaled display those differ, so derive
# the split from the bounds this process actually sees rather than hardcoding
# 1920x1080 - otherwise a 960 request lands as 1200 physical pixels.
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$halfW = [int]($bounds.Width / 2)
$fullH = $bounds.Height
Write-Host "[beat3] process-visible screen: $($bounds.Width)x$($bounds.Height); half=$halfW"

Write-Host "[beat3] clearing leftovers from any previous take"
Close-IsolatedChrome
Start-Sleep 2

Write-Host "[beat3] staging windows"
Move-Taskbar -Action park | Out-Null
Hide-ImeIndicators | Out-Null
Hide-SystemFlyouts | Out-Null

# Right half: the deployed dashboard, app mode, isolated profile.
Start-IsolatedChrome -Url $Dashboard -X $halfW -Y 0 -W $halfW -H $fullH -Windowed

# Left half: a console parked at a clean prompt. The replay command is typed
# into it on camera once ffmpeg is rolling, so the take shows the command run.
$startup = @(
    "`$env:GOOGLE_CLOUD_PROJECT='$Project'",
    "`$env:DILIGENCE_FIRESTORE_DATABASE='$Database'",
    "Set-Location '$repo'",
    "Clear-Host"
) -join "; "

$consoleTitle = "REPLAY-CONSOLE-$([guid]::NewGuid().ToString('N').Substring(0,6))"
$console = Start-StageConsole -Title $consoleTitle -StartupCommand $startup -NoExit

# Give the SPA time to boot before we fix its geometry.
Start-Sleep 6
$chromeWin = $null
$deadline = (Get-Date).AddSeconds(25)
while ((Get-Date) -lt $deadline) {
    $chromeWin = Get-TopLevelWindows |
        Where-Object { $_.Title -like "*Diligence Room*" -and $_.Title -notlike "REPLAY-CONSOLE*" } |
        Select-Object -First 1
    if ($chromeWin) { break }
    Start-Sleep -Milliseconds 400
}
if (-not $chromeWin) { throw "dashboard window never appeared - is the SPA serving?" }
$seam = 12
Set-WindowRect -Hwnd $chromeWin.Hwnd -X ($halfW - $seam) -Y 0 -W ($halfW + $seam) -H $fullH
Set-WindowTopmost -Hwnd $chromeWin.Hwnd
Write-Host "[beat3] dashboard staged: $($chromeWin.Title)"

# Console rect last so Chrome cannot steal position or z-order.
Set-WindowRect -Hwnd $console.Hwnd -X 0 -Y 0 -W $halfW -H $fullH
Set-WindowTopmost -Hwnd $console.Hwnd
Start-Sleep 2

if ($StageOnly) {
    $shot = Join-Path $takes "_stage.png"
    & $ffmpeg -hide_banner -loglevel error -y -f gdigrab -framerate 1 -draw_mouse 0 -i desktop -frames:v 1 $shot
    Write-Host "[beat3] StageOnly: nothing recorded; frame -> $shot"
    Move-Taskbar -Action restore | Out-Null
    return
}

$cmd = "uv run python scripts/video/replay_cli.py --live --deal-id deal-falcon --speed $Speed"

Write-Host "[beat3] rolling $Seconds s -> $out"
$ff = Start-Process -FilePath $ffmpeg -PassThru -ArgumentList @(
    "-hide_banner", "-loglevel", "error", "-y",
    "-f", "gdigrab", "-framerate", "30", "-draw_mouse", "0", "-i", "desktop",
    "-t", "$Seconds",
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p",
    $out
)

# Let the capture settle, then run the command on camera.
Start-Sleep 2
Focus-WindowForInput -Hwnd $console.Hwnd
Start-Sleep 1
[System.Windows.Forms.SendKeys]::SendWait($cmd)
Start-Sleep 1
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")

$ff.WaitForExit()
Write-Host "[beat3] capture done (exit $($ff.ExitCode))"
$dur = & $ffprobe -v error -show_entries format=duration -of csv=p=0 $out
Write-Host "[beat3] $out duration=$dur"

# Leave windows up: beats 4-7 reuse the populated dashboard.
Move-Taskbar -Action restore | Out-Null
