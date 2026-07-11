<#
  play.ps1 - one-click Assault launcher for Win11.

  What it does (all reverse-engineered this project):
    1. Ensures DDrawCompat's ddraw.dll is in the game folder. main.dat uses
       DirectDraw + Direct3D7, broken on Win11 -> crashes 0xC0000005 without it.
       cnc-ddraw does NOT work (2D only); DDrawCompat provides a D3D7 HAL.
    2. Starts the server emulator (assault_server.py) if not already running.
    3. Launches main.dat DIRECTLY, bypassing Assault.exe/Assault.dat.
       Why bypass: Assault.dat's "Connect" builds a broken command line
       (mangles the entry into 11+ tokens, truncates the IP) so main.dat rejects
       it with "Wrong parameter" (it requires argc == 8, i.e. exactly 7 tokens).
       We hand main.dat a clean 7-token arg instead.
    4. Pins the process to ONE cpu core -> dodges main.dat's fast-multicore
       startup race (children inherit the affinity).

  Usage:
    powershell -ExecutionPolicy Bypass -File .\play.ps1 [-User <id>] [-Pass <pw>]

  Prereq (one-time, as Administrator):  .\redirect.ps1
#>
param(
    [string]$User = "Assault",
    [string]$Pass = "nopass",
    [string]$ServerIP = "127.0.0.1",
    [int]$ServerPort = 11131
)
$ErrorActionPreference = "Stop"
$Game = "C:\Program Files (x86)\CodiNET\Assault"
$Here = $PSScriptRoot

# --- 1. DDrawCompat ddraw.dll (D3D7 HAL for Win11) ---------------------------
$ddraw = Join-Path $Game "ddraw.dll"
if (-not (Test-Path $ddraw) -or ((Get-Item $ddraw).Length -lt 2MB)) {
    $src = "C:\Program Files (x86)\Steam\steamapps\common\Command & Conquer Red Alert II\ddraw.dll"
    if (Test-Path $src) {
        Copy-Item $src $ddraw -Force
        Write-Host "Installed DDrawCompat ddraw.dll." -ForegroundColor Green
    } else {
        Write-Warning "DDrawCompat ddraw.dll not found - main.dat will crash. Put a DDrawCompat ddraw.dll in $Game."
    }
}

# --- 2. start the emulator (server) ------------------------------------------
if (-not (Get-Process python -ErrorAction SilentlyContinue)) {
    Start-Process py -ArgumentList "assault_server.py" -WorkingDirectory $Here -WindowStyle Minimized
    Start-Sleep -Seconds 2
    Write-Host "Emulator started." -ForegroundColor Green
} else {
    Write-Host "Emulator already running." -ForegroundColor DarkGray
}

# --- 3+4. launch main.dat directly, single-core, clean 7-token arg -----------
# arg tokens:  <id> <name> <pass> <flag> <ip> <port> <tail>
#   token2 -> login username, token3 -> login password,
#   token5 -> game-server IP, token6 -> game-server port.
$arg = "1 $User $Pass 1 $ServerIP $ServerPort 0"
$exe = Join-Path $Game "main.dat"

$si = New-Object System.Diagnostics.ProcessStartInfo
$si.FileName = $exe
$si.Arguments = $arg
$si.WorkingDirectory = $Game
$si.UseShellExecute = $false
$p = [System.Diagnostics.Process]::Start($si)
try { $p.ProcessorAffinity = [IntPtr]1 } catch {}
Write-Host "Launched main.dat (pid $($p.Id)) as '$User' -> ${ServerIP}:${ServerPort}, pinned to core 0." -ForegroundColor Cyan
Write-Host "arg: main.dat $arg" -ForegroundColor DarkGray
