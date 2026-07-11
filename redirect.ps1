<#
  redirect.ps1 - point the Assault client at our local capture harness.

  Backs up the original ini files + hosts, then rewrites the dead CodiNET
  server IPs / hostnames to 127.0.0.1. Run with -Restore to undo.

  Usage (run as Administrator):
      powershell -ExecutionPolicy Bypass -File redirect.ps1
      powershell -ExecutionPolicy Bypass -File redirect.ps1 -Restore
#>
# -Target is the emulator's IP the client should talk to:
#   127.0.0.1  (default) = emulator runs on THIS pc
#   <host IP>            = emulator runs on another pc (LAN/Hamachi/Radmin) -> point here
param([switch]$Restore, [string]$Target = "127.0.0.1")

$ErrorActionPreference = "Stop"
$Game   = "C:\Program Files (x86)\CodiNET\Assault"
$Backup = Join-Path $PSScriptRoot "backup"
$Hosts  = "$env:windir\System32\drivers\etc\hosts"
$Marker = "# ---- AssaultServer redirect ----"

# original CodiNET IP -> $Target (byte-level, preserves ANSI/cp949 encoding)
$IpMap = @{
    "203.248.248.54"  = $Target   # Server List
    "203.248.248.58"  = $Target   # Round
    "203.248.248.56"  = $Target   # Billing
    "61.74.201.227"   = $Target   # AutoPatch
    "211.40.79.79"    = $Target   # (commented alt list)
}
$IniFiles  = @("System.ini","Billing.ini","Patch.ini")
$HostNames = @("autopatch.codinet.com","assault.codinet.com","cgi.codinet.com")

function Backup-File($path) {
    if (-not (Test-Path $Backup)) { New-Item -ItemType Directory -Path $Backup | Out-Null }
    $dest = Join-Path $Backup (Split-Path $path -Leaf)
    if (-not (Test-Path $dest)) { Copy-Item $path $dest; Write-Host "  backed up -> $dest" }
}

function Replace-IpBytes($path) {
    $bytes = [System.IO.File]::ReadAllBytes($path)
    $text  = [System.Text.Encoding]::GetEncoding(1252).GetString($bytes)  # 1:1 byte<->char
    foreach ($k in $IpMap.Keys) { $text = $text.Replace($k, $IpMap[$k]) }
    [System.IO.File]::WriteAllBytes($path, [System.Text.Encoding]::GetEncoding(1252).GetBytes($text))
}

if ($Restore) {
    Write-Host "Restoring originals..." -ForegroundColor Cyan
    foreach ($f in $IniFiles) {
        $b = Join-Path $Backup $f
        if (Test-Path $b) { Copy-Item $b (Join-Path $Game $f) -Force; Write-Host "  restored $f" }
    }
    # strip our hosts block
    $lines = Get-Content $Hosts
    $out = New-Object System.Collections.Generic.List[string]
    $skip = $false
    foreach ($l in $lines) {
        if ($l -eq $Marker) { $skip = -not $skip; continue }
        if (-not $skip) { $out.Add($l) }
    }
    Set-Content -Path $Hosts -Value $out -Encoding Default
    Write-Host "  hosts cleaned" -ForegroundColor Green
    return
}

Write-Host "Redirecting Assault -> 127.0.0.1" -ForegroundColor Cyan
foreach ($f in $IniFiles) {
    $p = Join-Path $Game $f
    if (Test-Path $p) { Backup-File $p; Replace-IpBytes $p; Write-Host "  patched $f" }
    else { Write-Host "  (missing $f)" -ForegroundColor Yellow }
}

# hosts
Backup-File $Hosts
$content = Get-Content $Hosts -Raw
if ($content -notlike "*$Marker*") {
    $block = "`r`n$Marker`r`n"
    foreach ($h in $HostNames) { $block += "$Target`t$h`r`n" }
    $block += "$Marker`r`n"
    Add-Content -Path $Hosts -Value $block -Encoding Default
    Write-Host "  hosts entries added -> $Target" -ForegroundColor Green
} else {
    Write-Host "  hosts already has redirect block" -ForegroundColor Yellow
}

Write-Host "`nDone (target $Target). Now run:  .\play.ps1" -ForegroundColor Cyan
Write-Host "Undo later with: .\redirect.ps1 -Restore"
