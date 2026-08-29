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
[DllImport("user32.dll")] public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint processId);
[DllImport("user32.dll")] public static extern bool AttachThreadInput(uint idAttach, uint idAttachTo, bool fAttach);
[DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
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

function Focus-WindowForInput {
    # Robustly give a window keyboard focus. Windows blocks SetForegroundWindow
    # from background callers; the Alt keypress + AttachThreadInput combo
    # releases the foreground lock so SendKeys actually reaches the window.
    param([Parameter(Mandatory)][IntPtr]$Hwnd)
    [void][VideoWin32.User32]::ShowWindow($Hwnd, 5)  # SW_SHOW
    # Tap Alt to clear the foreground-lock timeout.
    [VideoWin32.User32]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero)   # Alt down
    [VideoWin32.User32]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)   # Alt up
    $null = $null
    $procId = [uint32]0
    $targetThread = [VideoWin32.User32]::GetWindowThreadProcessId($Hwnd, [ref]$procId)
    $myThread = [VideoWin32.User32]::GetCurrentThreadId()
    if ($targetThread -ne 0 -and $targetThread -ne $myThread) {
        [void][VideoWin32.User32]::AttachThreadInput($myThread, $targetThread, $true)
        [void][VideoWin32.User32]::SetForegroundWindow($Hwnd)
        [void][VideoWin32.User32]::AttachThreadInput($myThread, $targetThread, $false)
    } else {
        [void][VideoWin32.User32]::SetForegroundWindow($Hwnd)
    }
    Start-Sleep -Milliseconds 250
    $fg = [VideoWin32.User32]::GetForegroundWindow()
    return ($fg -eq $Hwnd)
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

function Start-IsolatedChrome {
    # Open a Chrome app window in a SEPARATE profile so the user's own Chrome
    # (and its tabs/login state) is never killed or touched. Returns nothing;
    # find the window afterwards via Find-WindowByTitle on the page title.
    param(
        [Parameter(Mandatory)][string]$Url,
        [int]$X = 0, [int]$Y = 0, [int]$W = 1920, [int]$H = 1080,
        # App mode hides the address bar. The hackathon rules ask for the
        # .run URL to be visible, so recordings use -Windowed.
        [switch]$Windowed
    )
    $chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
    $profile = Join-Path $env:LOCALAPPDATA "diligence_video_chrome_profile"
    $mode = if ($Windowed) { @("--new-window", $Url) } else { @("--app=$Url") }
    $cargs = @(
        "--user-data-dir=$profile"
    ) + $mode + @(
        "--window-position=$X,$Y",
        "--window-size=$W,$H",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-notifications",
        "--disable-session-crashed-bubble"
    )
    Start-Process -FilePath $chrome -ArgumentList $cargs
    Start-Sleep 4
}

function Set-WindowTopmost {
    param([Parameter(Mandatory)][IntPtr]$Hwnd)
    # HWND_TOPMOST (-1); SWP_NOSIZE|SWP_NOMOVE|SWP_SHOWWINDOW = 0x43
    [void][VideoWin32.User32]::SetWindowPos($Hwnd, [IntPtr]::new(-1), 0, 0, 0, 0, 0x43)
}

function Clear-WindowTopmost {
    param([Parameter(Mandatory)][IntPtr]$Hwnd)
    # HWND_NOTOPMOST (-2)
    [void][VideoWin32.User32]::SetWindowPos($Hwnd, [IntPtr]::new(-2), 0, 0, 0, 0, 0x43)
}

function Minimize-Window {
    param([Parameter(Mandatory)][IntPtr]$Hwnd)
    [void][VideoWin32.User32]::ShowWindow($Hwnd, 6)  # SW_MINIMIZE
}

function Clear-StageForRecording {
    # Minimize every top-level window that is not part of the recording set,
    # so desktop captures never catch the IDE or stray apps. Returns the hwnds
    # it minimized (so they can be restored later).
    param([string[]]$KeepTitleLikes = @())
    $minimized = @()
    foreach ($win in Get-TopLevelWindows) {
        $keep = $false
        foreach ($like in $KeepTitleLikes) { if ($win.Title -like "*$like*") { $keep = $true; break } }
        if ($keep) { continue }
        Minimize-Window -Hwnd $win.Hwnd
        $minimized += $win.Hwnd
    }
    Start-Sleep -Milliseconds 700
    return $minimized
}

function Restore-Minimized {
    param([IntPtr[]]$Hwnds)
    foreach ($h in $Hwnds) { [void][VideoWin32.User32]::ShowWindow($h, 9) }  # SW_RESTORE
}

function Hide-ImeIndicators {
    # When the taskbar is parked, topmost IME indicator windows
    # ("Default IME", "MSCTFIME UI") orphan and float over the frame bottom.
    # Hide every one of them before a take; they respawn only on IME use.
    $hidden = 0
    foreach ($win in Get-TopLevelWindows) {
        if ($win.Title -match "IME") {
            [void][VideoWin32.User32]::ShowWindow($win.Hwnd, 0)  # SW_HIDE
            $hidden++
        }
    }
    return $hidden
}

function Hide-SystemFlyouts {
    # Topmost tray flyouts (Battery Meter, Network Flyout, etc.) ignore
    # SW_MINIMIZE and float over captures; hide them by title pattern.
    $patterns = @("*Battery*", "*Network Flyout*", "*Clock*", "*Volume*", "*Action Center*", "*Calendar*")
    $hidden = 0
    foreach ($win in Get-TopLevelWindows) {
        foreach ($p in $patterns) {
            if ($win.Title -like $p) {
                [void][VideoWin32.User32]::ShowWindow($win.Hwnd, 0)  # SW_HIDE
                $hidden++
                break
            }
        }
    }
    return $hidden
}

function Resolve-Ffmpeg {
    # Start-Process resolves against the Windows PATH, which is not always what
    # the calling shell exported. Resolve to an absolute path once and fail
    # loudly instead of throwing a bare Win32Exception mid-take.
    param([string]$Name = "ffmpeg")
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($candidate in @(
        "C:fmpegin\$Name.exe",
        "C:\Program Filesfmpegin\$Name.exe"
    )) {
        if (Test-Path $candidate) { return $candidate }
    }
    throw "$Name not found on PATH or in C:fmpegin - add it before recording"
}

function Clear-IsolatedChromeCrashState {
    # The recording profile is force-killed between takes, which marks it
    # exit_type=Crashed and brings up the restore bubble on the next launch.
    # Clear-ChromeCrashState only covers the user's default profile.
    $root = Join-Path $env:LOCALAPPDATA "diligence_video_chrome_profile"
    if (-not (Test-Path $root)) { return }
    Get-ChildItem $root -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match "^(Default|Profile )" } |
        ForEach-Object {
            $prefs = Join-Path $_.FullName "Preferences"
            if (-not (Test-Path $prefs)) { return }
            try {
                $j = Get-Content $prefs -Raw | ConvertFrom-Json
                if ($j.profile) {
                    $j.profile.exit_type = "Normal"
                    $j.profile | Add-Member -NotePropertyName exited_cleanly -NotePropertyValue $true -Force
                    $j | ConvertTo-Json -Depth 40 -Compress | Set-Content $prefs -Encoding utf8 -NoNewline
                }
            } catch {
                Write-Host "[chrome] could not reset isolated crash state: $_"
            }
        }
}

function Close-IsolatedChrome {
    # Ask the recording profile's windows to close, then force only what is
    # left. Killing outright is what corrupts the profile between takes.
    $procs = @(Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" |
        Where-Object { $_.CommandLine -like "*diligence_video_chrome_profile*" })
    if (-not $procs) { return }
    foreach ($p in $procs) {
        # A Chrome child can exit between the query and this call; touching
        # MainWindowHandle on an exited process throws InvalidOperationException
        # and aborts the take.
        try {
            $handle = Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue
            if ($handle -and -not $handle.HasExited -and $handle.MainWindowHandle -ne 0) {
                [void]$handle.CloseMainWindow()
            }
        } catch {
            # already gone; nothing to close
        }
    }
    Start-Sleep 2
    foreach ($p in $procs) {
        try { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue } catch { }
    }
    Start-Sleep 1
    Clear-IsolatedChromeCrashState
}
