# Frame QA: extracts 1fps PNG frames from a take for visual inspection.
# Usage: scripts/video/qa_frames.ps1 -Beat 3 -Take 1

param(
    [Parameter(Mandatory)][int]$Beat,
    [int]$Take = 0,
    [double]$Fps = 1,
    [string]$TakesDir = "$PSScriptRoot/../../docs/video/takes",
    [string]$QaDir = "$PSScriptRoot/../../docs/video/qa",
    [string]$Source = ""
)

$ErrorActionPreference = "Stop"
if ($Source -eq "") {
    if ($Take -eq 0) { throw "pass -Take N or -Source path" }
    $Source = Join-Path (Resolve-Path $TakesDir) "beat${Beat}_take${Take}.mkv"
}
$name = [System.IO.Path]::GetFileNameWithoutExtension($Source)
$outDir = Join-Path (Resolve-Path $QaDir) $name
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

& ffmpeg -hide_banner -loglevel error -y -i $Source -vf "fps=$Fps" "$outDir/frame_%04d.png"
if ($LASTEXITCODE -ne 0) { throw "frame extraction failed (exit $LASTEXITCODE)" }
$count = (Get-ChildItem $outDir -Filter *.png | Measure-Object).Count
Write-Host "[qa] $count frames -> $outDir"
