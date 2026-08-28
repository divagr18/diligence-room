# Title card + lower-third generation (ffmpeg drawtext, #0a0a0b theme).
# Usage: scripts/video/cards.ps1 -All

param([switch]$All)

$ErrorActionPreference = "Stop"
$cards = Join-Path (Resolve-Path "$PSScriptRoot/../../docs/video") "cards"
New-Item -ItemType Directory -Force -Path $cards | Out-Null
$font = "C\:/Windows/Fonts/segoeui.ttf"
$fontBold = "C\:/Windows/Fonts/segoeuib.ttf"
$bg = "0x0a0a0b"
$fg = "0xe8e8ea"
$accent = "0x7aa2f7"
$muted = "0x9a9aa2"

function New-TitleCard {
    $out = Join-Path $cards "title.mp4"
    $t1 = "drawtext=fontfile='$fontBold':text='Diligence Room':fontcolor=$fg" + ":fontsize=96:x=(w-text_w)/2:y=(h/2)-120"
    $t2 = "drawtext=fontfile='$font':text='Zero-trust runtime for autonomous institutional agent fleets':fontcolor=$accent" + ":fontsize=36:x=(w-text_w)/2:y=(h/2)+20"
    $t3 = "drawtext=fontfile='$font':text='AllThingsAgentic Hackathon - Fortified Enterprise Fleet':fontcolor=$muted" + ":fontsize=28:x=(w-text_w)/2:y=(h/2)+90"
    $vf = "$t1,$t2,$t3,fade=t=in:st=0:d=0.5,fade=t=out:st=2.5:d=0.5"
    & ffmpeg -hide_banner -loglevel error -y -f lavfi -i "color=c=${bg}:s=1920x1080:d=3" -vf $vf -c:v libx264 -preset medium -crf 17 -pix_fmt yuv420p -r 30 $out
    if ($LASTEXITCODE -ne 0) { throw "title card render failed" }
    Write-Host "[cards] $out"
}

function New-LowerThird {
    param([string]$Text, [string]$Name)
    $out = Join-Path $cards "$Name.png"
    $esc = $Text -replace ":", "\:"
    $vf = "drawtext=fontfile='$font':text='$esc':fontcolor=$fg" + ":fontsize=30:x=40:y=h-70:box=1:boxcolor=black@0.65:boxborderw=14"
    & ffmpeg -hide_banner -loglevel error -y -f lavfi -i "color=c=black@0.0:s=1920x1080" -frames:v 1 -vf $vf $out
    if ($LASTEXITCODE -ne 0) { throw "lower third '$Name' render failed" }
    Write-Host "[cards] $out"
}

if ($All) {
    New-TitleCard
    New-LowerThird -Name "b1" -Text "The twist: documents are adversaries"
    New-LowerThird -Name "b2" -Text "Agent Registry: discovery, versions, approval"
    New-LowerThird -Name "b3" -Text "Unedited execution: real pipeline, deterministic replay"
    New-LowerThird -Name "b4" -Text "Governed cooperation through the Agent Gateway"
    New-LowerThird -Name "b5" -Text "Model Armor + Gemma sentinel: 20/20 attacks blocked"
    New-LowerThird -Name "b6" -Text "Upgrade, catch the regression, roll back - memory intact"
    New-LowerThird -Name "b7" -Text "Human approval gate + end-to-end audit trail"
}
