# Tight-staging recording helpers: enter stage -> capture -> restore, so no
# windows linger between takes. Dot-sources windows.ps1.
#
# IMPORTANT: this never minimizes or restores the user's own windows. The
# recording windows are made topmost and cover the full screen instead, so
# the user's desktop is left exactly as they had it. Only always-on-top
# system chrome (taskbar, IME indicators, tray flyouts) is hidden, because
# those render over everything regardless of z-order.
#
#   Enter-RecordingStage                       # park taskbar, hide IME/flyouts
#   $cap = Start-TakeCapture -Beat 3 -Take 1 -Seconds 48
#   ... mid-take interaction ...
#   Wait-TakeCapture $cap
#   Exit-RecordingStage -CloseTitleLikes @("...")   # close beat windows, restore taskbar

. "$PSScriptRoot/lib/windows.ps1"

# Video base dir: honor $env:DILIGENCE_VIDEO_DIR so takes/final can live on a
# drive with free space (the repo drive can be full). Defaults to docs/video.
function Get-VideoBase {
    if ($env:DILIGENCE_VIDEO_DIR) { return (Resolve-Path $env:DILIGENCE_VIDEO_DIR).Path }
    return (Join-Path (Resolve-Path "$PSScriptRoot/../..") "docs/video")
}
function Get-TakesDir {
    $d = Join-Path (Get-VideoBase) "takes"
    New-Item -ItemType Directory -Force -Path $d | Out-Null
    return $d
}

$script:StageStateFile = Join-Path (Get-TakesDir) "stage-state.json"

function Enter-RecordingStage {
    param([string[]]$KeepTitleLikes = @())
    # Do NOT minimize the user's windows; recording windows are topmost and
    # cover the screen instead. Only hide always-on-top system chrome.
    Move-Taskbar -Action park
    $ime = Hide-ImeIndicators
    $fly = Hide-SystemFlyouts
    @{ minimized = @(); ime = $ime; fly = $fly } | ConvertTo-Json -Depth 4 | Set-Content $script:StageStateFile -Encoding utf8
    Write-Host "[stage] entered: hid $ime IME + $fly flyouts (user windows untouched)"
}

function Exit-RecordingStage {
    param([string[]]$CloseTitleLikes = @())
    # Close only this beat's own windows (matched by title).
    foreach ($like in $CloseTitleLikes) {
        foreach ($win in @(Get-TopLevelWindows | Where-Object { $_.Title -like "*$like*" })) {
            $p = Get-Process | Where-Object { $_.MainWindowHandle -eq $win.Hwnd } | Select-Object -First 1
            if ($p) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
        }
    }
    if (Test-Path $script:StageStateFile) { Remove-Item $script:StageStateFile -ErrorAction SilentlyContinue }
    Move-Taskbar -Action restore
    Write-Host "[stage] exited: closed recording windows, restored taskbar"
}

function Start-TakeCapture {
    param(
        [Parameter(Mandatory)][int]$Beat,
        [Parameter(Mandatory)][int]$Take,
        [Parameter(Mandatory)][int]$Seconds,
        [switch]$ShowMouse,
        [int]$Countdown = 3
    )
    $repo = Resolve-Path "$PSScriptRoot/../.."
    $out = Join-Path (Get-TakesDir) "beat${Beat}_take${Take}.mkv"
    $drawMouse = if ($ShowMouse) { 1 } else { 0 }
    for ($i = $Countdown; $i -ge 1; $i--) { Write-Host "[capture] $i"; Start-Sleep 1 }
    $proc = Start-Process -FilePath "ffmpeg" -ArgumentList @(
        "-hide_banner", "-loglevel", "error", "-y",
        "-f", "gdigrab", "-framerate", "30", "-draw_mouse", "$drawMouse", "-i", "desktop",
        "-t", "$Seconds",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p",
        $out
    ) -PassThru
    Write-Host "[capture] rolling beat=$Beat take=$Take seconds=$Seconds pid=$($proc.Id) -> $out"
    return @{ Proc = $proc; Out = $out; Beat = $Beat; Take = $Take }
}

function Wait-TakeCapture {
    param([hashtable]$Cap)
    $Cap.Proc.WaitForExit()
    if ($Cap.Proc.ExitCode -ne 0) { throw "capture failed for beat $($Cap.Beat) take $($Cap.Take) (exit $($Cap.Proc.ExitCode))" }
    $dur = & ffprobe -v error -show_entries format=duration -of csv=p=0 $Cap.Out
    Write-Host "[capture] done beat=$($Cap.Beat) take=$($Cap.Take) duration=${dur}s"
    return $Cap.Out
}
