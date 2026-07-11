<#
  play.ps1 - one-command Assault launcher (host / client / dedicated-server).

  Roles (auto-detected from -ServerIP):
    * -ServerIP is THIS pc (127.0.0.1 or one of my own IPs)  -> HOST+PLAY:
        starts the emulator, opens the firewall, then launches the game locally.
    * -ServerIP is a REMOTE pc                               -> CLIENT:
        does NOT start the emulator; points billing at the host and launches
        the game against the host's emulator.
    * -ServerOnly                                            -> DEDICATED SERVER:
        starts the emulator + firewall only (host runs this; friends then use
        `.\play.ps1 -ServerIP <hostIP>`).

  Examples:
    .\play.ps1                                  # solo, everything on this pc
    .\play.ps1 -ServerOnly                      # run the server for friends
    .\play.ps1 -ServerIP 25.12.95.154 -User me -Pass pw   # join a friend's host

  NOTE (honest): the emulator does NOT yet sync two clients into the same room,
  so this only gets a second pc to LOG IN to the host - real 2-player battles
  still need the room/match/P2P protocol. Firewall/emulator steps need admin.

  Prereq (host, one-time): .\redirect.ps1
#>
param(
    [string]$ServerIP  = "127.0.0.1",
    [string]$User      = "Assault",
    [string]$Pass      = "nopass",
    [int]   $Port      = 11131,
    [switch]$ServerOnly
)
$ErrorActionPreference = "Stop"
$Game = "C:\Program Files (x86)\CodiNET\Assault"
$Here = $PSScriptRoot

function Test-Local([string]$ip) {
    if ($ip -in @("127.0.0.1", "localhost", "::1")) { return $true }
    $mine = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue).IPAddress
    return ($mine -contains $ip)
}
$isHost = $ServerOnly -or (Test-Local $ServerIP)

# --- firewall + emulator (host / dedicated-server only) ----------------------
if ($isHost) {
    try {
        Remove-NetFirewallRule -DisplayName "Assault Emu" -ErrorAction SilentlyContinue
        New-NetFirewallRule -DisplayName "Assault Emu" -Direction Inbound -Protocol TCP `
            -LocalPort 10131,10525,10905,11131,9011 -Action Allow | Out-Null
        Write-Host "Firewall opened for the emulator ports." -ForegroundColor Green
    } catch { Write-Warning "Could not open the firewall (run as Administrator to allow remote clients)." }

    if (-not (Get-Process python -ErrorAction SilentlyContinue)) {
        $adv = if ($ServerOnly) { @("--advertise-ip", ((Get-NetIPAddress -AddressFamily IPv4 |
                 Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
                 Select-Object -First 1).IPAddress)) } else { @() }
        Start-Process py -ArgumentList (@("assault_server.py") + $adv) -WorkingDirectory $Here -WindowStyle Minimized
        Start-Sleep -Seconds 2
        Write-Host "Emulator started." -ForegroundColor Green
    } else { Write-Host "Emulator already running." -ForegroundColor DarkGray }
}

if ($ServerOnly) {
    $ips = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
                $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" }).IPAddress
    Write-Host ""
    Write-Host "Dedicated server running. Friends join with:" -ForegroundColor Cyan
    foreach ($ip in $ips) { Write-Host "    .\play.ps1 -ServerIP $ip -User <id> -Pass <pw>" }
    return
}

# --- DDrawCompat ddraw.dll (needed on EVERY pc that runs the game) ------------
$ddraw = Join-Path $Game "ddraw.dll"
if (-not (Test-Path $ddraw) -or ((Get-Item $ddraw).Length -lt 2MB)) {
    $src = "C:\Program Files (x86)\Steam\steamapps\common\Command & Conquer Red Alert II\ddraw.dll"
    if (Test-Path $src) { Copy-Item $src $ddraw -Force; Write-Host "Installed DDrawCompat ddraw.dll." -ForegroundColor Green }
    else { Write-Warning "DDrawCompat ddraw.dll missing - the game will crash on Win11. Put a DDrawCompat ddraw.dll in $Game." }
}

# --- point the billing/login server (Billing.ini) at $ServerIP ----------------
$billing = Join-Path $Game "Billing.ini"
if (Test-Path $billing) {
    $txt = [System.IO.File]::ReadAllText($billing)
    $new = [regex]::Replace($txt, '(?m)^(BI\s*=).*$', "`${1}$ServerIP")
    if ($new -ne $txt) { [System.IO.File]::WriteAllText($billing, $new); Write-Host "Billing.ini -> $ServerIP" -ForegroundColor DarkGray }
}

# --- launch main.dat directly, single-core, clean 7-token arg -----------------
$arg = "1 $User $Pass 1 $ServerIP $Port 0"
$si = New-Object System.Diagnostics.ProcessStartInfo
$si.FileName = Join-Path $Game "main.dat"
$si.Arguments = $arg
$si.WorkingDirectory = $Game
$si.UseShellExecute = $false
$p = [System.Diagnostics.Process]::Start($si)
try { $p.ProcessorAffinity = [IntPtr]1 } catch {}
$role = if (Test-Local $ServerIP) { "HOST" } else { "CLIENT -> $ServerIP" }
Write-Host "Launched main.dat (pid $($p.Id)) [$role] as '$User' -> ${ServerIP}:${Port}, core 0." -ForegroundColor Cyan
