# Final assembly: trim + normalize per-beat takes, overlay lower-thirds
# (+ beat-4 cameo), prepend title card, concat, mux silent AAC.
#
# Driven by docs/video/takes/selection.json:
#   { "beats": [ {"beat":1,"take":"beat1_take2.mkv","in":0.0,"dur":24.0}, ... ],
#     "cameo": {"take":"cameo.mkv","beat":4,"scale":"560:315"} }
#
# Usage: scripts/video/assemble.ps1 [-Selection path] [-Out final.mp4]

param(
    [string]$Selection = "$PSScriptRoot/../../docs/video/takes/selection.json",
    [string]$Out = "$PSScriptRoot/../../docs/video/final/diligence-room-demo.mp4",
    [string]$CardsDir = "$PSScriptRoot/../../docs/video/cards"
)

$ErrorActionPreference = "Stop"
$repo = Resolve-Path "$PSScriptRoot/../.."
$takes = Join-Path $repo "docs/video/takes"
$work = Join-Path $repo "docs/video/final/work"
New-Item -ItemType Directory -Force -Path $work | Out-Null
$CardsDir = Resolve-Path $CardsDir

function Run-Ffmpeg { param([string[]]$Fargs) & ffmpeg @Fargs 2>&1 | Out-Null; if ($LASTEXITCODE -ne 0) { throw "ffmpeg failed: $($Fargs -join ' ')" } }

function Normalize-Segment {
    param([string]$Src, [double]$In, [double]$Dur, [string]$LowerThird, [string]$OutSeg)
    $vf = "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p[base]"
    $maps = "[base]"
    if ($LowerThird -and (Test-Path $LowerThird)) {
        $vf += ";[base][1:v]overlay=0:0:enable='lt(t,2.5)'[ovl]"
        $maps = "[ovl]"
    }
    $srcArgs = @("-hide_banner", "-loglevel", "error", "-y", "-ss", "$In", "-t", "$Dur", "-i", $Src)
    if ($LowerThird -and (Test-Path $LowerThird)) { $srcArgs += @("-i", $LowerThird) }
    $enc = @("-filter_complex", $vf, "-map", $maps, "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-r", "30", $OutSeg)
    Run-Ffmpeg ($srcArgs + $enc)
    return $OutSeg
}

Write-Host "[assemble] reading selection: $Selection"
$sel = Get-Content $Selection -Raw | ConvertFrom-Json
$beatSegs = @()

foreach ($b in ($sel.beats | Sort-Object beat)) {
    $src = Join-Path $takes $b.take
    if (-not (Test-Path $src)) { throw "missing take for beat $($b.beat): $src" }
    $lt = Join-Path $CardsDir ("b" + $b.beat + ".png")
    $outSeg = Join-Path $work ("seg" + $b.beat + ".mp4")

    # Beat 4 gets the failure-tolerance cameo overlaid bottom-right for its last 10s.
    if ($b.beat -eq 4 -and $sel.cameo) {
        $csrc = Join-Path $takes $sel.cameo.take
        if (-not (Test-Path $csrc)) { throw "missing cameo: $csrc" }
        $cscale = if ($sel.cameo.scale) { $sel.cameo.scale } else { "560:315" }
        $cstart = [Math]::Max(0, $b.dur - 10)
        $vf = "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p[base]"
        $vf += ";[2:v]scale=$cscale,format=yuv420p[cam]"
        $vf += ";[base][1:v]overlay=0:0:enable='lt(t,2.5)'[ovl]"
        $vf += ";[ovl][cam]overlay=x=W-w-24:y=H-h-24:enable='gte(t,$cstart)'[fin]"
        $fargs = @("-hide_banner", "-loglevel", "error", "-y",
            "-ss", "$($b.in)", "-t", "$($b.dur)", "-i", $src,
            "-i", $lt, "-i", $csrc,
            "-filter_complex", $vf, "-map", "[fin]", "-an",
            "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-r", "30", $outSeg)
        Run-Ffmpeg $fargs
    } else {
        Normalize-Segment -Src $src -In $b.in -Dur $b.dur -LowerThird $lt -OutSeg $outSeg | Out-Null
    }
    Write-Host "[assemble] beat $($b.beat) -> $outSeg (dur $($b.dur))"
    $beatSegs += $outSeg
}

# Normalize the title card to identical stream params.
$titleSrc = Join-Path $CardsDir "title.mp4"
$titleSeg = Join-Path $work "seg0.mp4"
Run-Ffmpeg @("-hide_banner", "-loglevel", "error", "-y", "-i", $titleSrc,
    "-vf", "scale=1920:1080,fps=30,format=yuv420p", "-an",
    "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-r", "30", $titleSeg)
Write-Host "[assemble] title -> $titleSeg"

# Concat list: title first, then beats in order.
$concatList = Join-Path $work "concat.txt"
$lines = @("file '$titleSeg'")
foreach ($s in $beatSegs) { $lines += "file '$s'" }
$lines | Set-Content $concatList -Encoding ascii
$concatVid = Join-Path $work "concat_video.mp4"
Run-Ffmpeg @("-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", $concatList, "-c", "copy", $concatVid)
Write-Host "[assemble] concat -> $concatVid"

# Mux silent AAC audio.
$Out = [System.IO.Path]::GetFullPath($Out)
New-Item -ItemType Directory -Force -Path (Split-Path $Out) | Out-Null
Run-Ffmpeg @("-hide_banner", "-loglevel", "error", "-y", "-i", $concatVid,
    "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
    "-shortest", $Out)
Write-Host "[assemble] FINAL -> $Out"

# QA report.
$dur = & ffprobe -v error -show_entries format=duration -of csv=p=0 $Out
$stream = & ffprobe -v error -select_streams v:0 -show_entries stream=width,height,codec_name,pix_fmt,r_frame_rate -of json $Out
$astream = & ffprobe -v error -select_streams a:0 -show_entries stream=codec_name,sample_rate,channels -of json $Out
Write-Host "[assemble][qa] duration_s=$dur"
Write-Host "[assemble][qa] video=$stream"
Write-Host "[assemble][qa] audio=$astream"
