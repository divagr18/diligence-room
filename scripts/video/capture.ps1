# Beat capture: records the full desktop via gdigrab into takes/.
# Usage: scripts/video/capture.ps1 -Beat 3 -Take 1 -Seconds 60

param(
    [Parameter(Mandatory)][int]$Beat,
    [Parameter(Mandatory)][int]$Take,
    [Parameter(Mandatory)][int]$Seconds,
    [string]$OutDir = "$PSScriptRoot/../../docs/video/takes",
    [switch]$ShowMouse
)

$ErrorActionPreference = "Stop"
$repo = Resolve-Path "$PSScriptRoot/../.."
$out = Join-Path (Resolve-Path $OutDir) "beat${Beat}_take${Take}.mkv"
$drawMouse = if ($ShowMouse) { 1 } else { 0 }

Write-Host "[capture] beat=$Beat take=$Take seconds=$Seconds mouse=$drawMouse -> $out"
Write-Host "[capture] starting in 3..."; Start-Sleep 1
Write-Host "[capture] 2..."; Start-Sleep 1
Write-Host "[capture] 1..."; Start-Sleep 1

& ffmpeg -hide_banner -loglevel error -y `
    -f gdigrab -framerate 30 -draw_mouse $drawMouse -i desktop `
    -t $Seconds `
    -c:v libx264 -preset veryfast -crf 16 -pix_fmt yuv420p `
    $out

if ($LASTEXITCODE -ne 0) { throw "ffmpeg capture failed (exit $LASTEXITCODE)" }
$dur = & ffprobe -v error -show_entries format=duration -of csv=p=0 $out
Write-Host "[capture] done: $out duration=${dur}s"
