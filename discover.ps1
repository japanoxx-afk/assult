<#
  discover.ps1 - find which ports the client actually talks to.

  Two methods:
   1. pktmon  (loopback packet capture, catches TCP *and* UDP dest ports)
   2. netstat watcher (quick, TCP only, shows connection attempts live)

  Usage (Administrator):
      .\discover.ps1 -Start          # begin pktmon loopback capture
      ...launch game, reproduce...
      .\discover.ps1 -Stop           # stop + export txt/pcapng to .\captures
      .\discover.ps1 -Watch          # live netstat of game's TCP connections (Ctrl+C to stop)
#>
param([switch]$Start,[switch]$Stop,[switch]$Watch)

$Cap = Join-Path $PSScriptRoot "captures"
if (-not (Test-Path $Cap)) { New-Item -ItemType Directory -Path $Cap | Out-Null }
$Etl = Join-Path $Cap "pktmon.etl"

if ($Start) {
    pktmon stop 2>$null | Out-Null
    if (Test-Path $Etl) { Remove-Item $Etl -Force }
    # capture all components incl. loopback, full payload
    pktmon start --capture --pkt-size 0 --file $Etl
    Write-Host "pktmon capturing -> $Etl  (run game, then: discover.ps1 -Stop)" -ForegroundColor Cyan
    return
}

if ($Stop) {
    pktmon stop
    $txt = Join-Path $Cap "pktmon.txt"
    $pcap = Join-Path $Cap "pktmon.pcapng"
    pktmon etl2txt $Etl -o $txt
    pktmon pcapng $Etl -o $pcap 2>$null
    Write-Host "Exported:`n  $txt`n  $pcap" -ForegroundColor Green
    Write-Host "Open the .pcapng in Wireshark, or grep the .txt for 127.0.0.1 ports."
    return
}

if ($Watch) {
    Write-Host "Watching Assault TCP connections (Ctrl+C to stop)..." -ForegroundColor Cyan
    $seen = @{}
    while ($true) {
        $procs = Get-Process | Where-Object { $_.ProcessName -match 'Assault|Fork|Match|Patch' } | Select-Object -Expand Id
        foreach ($id in $procs) {
            Get-NetTCPConnection -OwningProcess $id -ErrorAction SilentlyContinue | ForEach-Object {
                $key = "$($_.RemoteAddress):$($_.RemotePort) [$($_.State)]"
                if (-not $seen.ContainsKey($key)) {
                    $seen[$key] = $true
                    $pn = (Get-Process -Id $id -ErrorAction SilentlyContinue).ProcessName
                    Write-Host ("  {0,-14} -> {1}" -f $pn, $key) -ForegroundColor Yellow
                }
            }
        }
        Start-Sleep -Milliseconds 500
    }
}

Write-Host "Specify -Start | -Stop | -Watch"
