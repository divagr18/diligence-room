# Window staging helpers for demo recording (scripts/video).
# Dot-source: . scripts/video/lib/windows.ps1

Add-Type -Namespace VideoWin32 -Name User32 -MemberDefinition @'
[DllImport("user32.dll")] public static extern IntPtr FindWindow(string cls, string title);
[DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hwnd, IntPtr insertAfter, int x, int y, int cx, int cy, uint flags);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hwnd);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hwnd, int cmd);
[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
[DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hwnd, System.Text.StringBuilder s, int n);
[DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc cb, IntPtr l);
public delegate bool EnumWindowsProc(IntPtr hwnd, IntPtr l);
'@

$script:SWP_NOZORDER = 0x4
$script:SW_RESTORE = 9
$script:SW_SHOWMAXIMIZED = 3

function Get-TopLevelWindows {
    $found = New-Object System.Collections.Generic.List[object]
    $cb = [VideoWin32.User32+EnumWindowsProc]{
        param($hwnd, $l)
        $sb = New-Object System.Text.StringBuilder 512
        [void][VideoWin32.User32]::GetWindowText($hwnd, $sb, 512)
        if ($sb.Length -gt 0) { $found.Add([pscustomobject]@{ Hwnd = $hwnd; Title = $sb.ToString() }) }
        return $true
    }
    [void][VideoWin32.User32]::EnumWindows($cb, [IntPtr]::Zero)
    return $found
}

function Find-WindowByTitle {
    param([Parameter(Mandatory)][string]$Like)
    return Get-TopLevelWindows | Where-Object { $_.Title -like "*$Like*" } | Select-Object -First 1
}

function Set-WindowRect {
    param(
        [Parameter(Mandatory)][IntPtr]$Hwnd,
        [int]$X, [int]$Y, [int]$W, [int]$H
    )
    [void][VideoWin32.User32]::ShowWindow($Hwnd, $script:SW_RESTORE)
    $ok = [VideoWin32.User32]::SetWindowPos($Hwnd, [IntPtr]::Zero, $X, $Y, $W, $H, 0)
    if (-not $ok) { throw "SetWindowPos failed for hwnd $Hwnd" }
}

function Invoke-WindowFocus {
    param([Parameter(Mandatory)][IntPtr]$Hwnd)
    [void][VideoWin32.User32]::SetForegroundWindow($Hwnd)
}

function Set-WindowMaximized {
    param([Parameter(Mandatory)][IntPtr]$Hwnd)
    [void][VideoWin32.User32]::ShowWindow($Hwnd, $script:SW_SHOWMAXIMIZED)
}

function Move-Taskbar {
    param([ValidateSet("park", "restore")][string]$Action = "park")
    $tray = [VideoWin32.User32]::FindWindow("Shell_TrayWnd", $null)
    if ($tray -eq [IntPtr]::Zero) { return }
    if ($Action -eq "park") {
        # Hide outright (SW_HIDE) and also push below the 1080p edge as
        # belt-and-suspenders so no sliver renders over captures.
        [void][VideoWin32.User32]::ShowWindow($tray, 0)
        [void][VideoWin32.User32]::SetWindowPos($tray, [IntPtr]::Zero, 0, 1440, 1920, 48, 0x4)
    } else {
        [void][VideoWin32.User32]::SetWindowPos($tray, [IntPtr]::Zero, 0, 1032, 1920, 48, 0x4)
        [void][VideoWin32.User32]::ShowWindow($tray, 5)
    }
}

function Set-ConsoleDefaults {
    # Large readable font for new conhost windows (half-screen legibility).
    $key = "HKCU:\Console"
    Set-ItemProperty -Path $key -Name "FaceName" -Value "Consolas" -Type String
    Set-ItemProperty -Path $key -Name "FontFamily" -Value 54 -Type DWord
    Set-ItemProperty -Path $key -Name "FontHeight" -Value 28 -Type DWord
    Set-ItemProperty -Path $key -Name "FontWidth" -Value 0 -Type DWord
    # Window 96 cols x 30 rows; buffer rows 300 for scrollback.
    Set-ItemProperty -Path $key -Name "WindowSize" -Value ((96 -shl 16) -bor 30) -Type DWord
    Set-ItemProperty -Path $key -Name "ScreenBufferSize" -Value ((96 -shl 16) -bor 300) -Type DWord
}

function Start-StageConsole {
    param(
        [Parameter(Mandatory)][string]$Title,
        [string]$StartupCommand = "",
        [switch]$NoExit
    )
    $body = "`$Host.UI.RawUI.WindowTitle = '$Title'"
    if ($StartupCommand) { $body += "; $StartupCommand" }
    if ($NoExit) { $body += "" }
    $args = @("-NoLogo", "-NoProfile", "-Command", $body)
    if ($NoExit) { $args = @("-NoLogo", "-NoProfile", "-NoExit", "-Command", $body) }
    Start-Process -FilePath "powershell.exe" -ArgumentList $args
    $deadline = (Get-Date).AddSeconds(15)
    while ((Get-Date) -lt $deadline) {
        $w = Find-WindowByTitle -Like $Title
        if ($w) { return $w }
        Start-Sleep -Milliseconds 300
    }
    throw "console window '$Title' did not appear within 15s"
}

function Start-StageChrome {
    param(
        [Parameter(Mandatory)][string]$Url,
        [int]$X = 0, [int]$Y = 0, [int]$W = 1920, [int]$H = 1080
    )
    $chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
    Start-Process -FilePath $chrome -ArgumentList @(
        "--new-window",
        "--window-position=$X,$Y",
        "--window-size=$W,$H",
        "--disable-notifications",
        "--no-first-run",
        "--no-default-browser-check",
        $Url
    )
}

function Clear-ChromeCrashState {
    # A force-killed Chrome marks every profile exit_type=Crashed, which makes
    # the next launch show the "Restore pages?" bubble (a recording artifact).
    # Reset exit_type while Chrome is not running so launches come up clean.
    $ud = Join-Path $env:LOCALAPPDATA "Google\Chrome\User Data"
    Get-ChildItem $ud -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match "^(Default|Profile )" } |
        ForEach-Object {
            $p = Join-Path $_.FullName "Preferences"
            if (-not (Test-Path $p)) { return }
            try {
                $j = Get-Content $p -Raw | ConvertFrom-Json
                if ($j.profile) {
                    $j.profile.exit_type = "Normal"
                    $j.profile | Add-Member -NotePropertyName exited_cleanly -NotePropertyValue $true -Force
                    $j | ConvertTo-Json -Depth 40 -Compress | Set-Content $p -Encoding utf8 -NoNewline
                }
            } catch {
                Write-Host "[chrome] could not reset crash state in $p : $_"
            }
        }
}

function Restart-CleanChrome {
    param(
        [Parameter(Mandatory)][string]$Url,
        [ValidateSet("app", "window", "fullscreen")][string]$Mode = "app",
        [int]$X = 0, [int]$Y = 0, [int]$W = 1920, [int]$H = 1080
    )
    Get-Process chrome -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Milliseconds 1500
    Clear-ChromeCrashState
    $chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
    $cargs = @("--disable-notifications", "--no-first-run", "--no-default-browser-check")
    switch ($Mode) {
        "app" { $cargs += "--app=$Url" }
        "fullscreen" { $cargs += "--start-fullscreen"; $cargs += $Url }
        "window" { $cargs += @("--new-window", "--window-position=$X,$Y", "--window-size=$W,$H"); $cargs += $Url }
    }
    Start-Process -FilePath $chrome -ArgumentList $cargs
    $deadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $deadline) {
        $procs = Get-Process chrome -ErrorAction SilentlyContinue
        if ($procs) { break }
        Start-Sleep -Milliseconds 300
    }
    Start-Sleep 2
}
