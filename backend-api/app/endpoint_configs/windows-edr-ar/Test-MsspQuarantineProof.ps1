#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Proof checklist for MSSP host network quarantine (standalone / no-GPO lab).

.DESCRIPTION
  Run BEFORE isolate (baseline) and AFTER isolate (within ~60s of portal Isolate).
  Pass = default-deny outbound on all profiles + LAN probes fail + Manager path OK.
#>
param(
  [string]$ManagerIp = "192.168.0.211",
  [string]$GatewayIp = ""
)

Write-Host "=== MSSP quarantine proof ===" -ForegroundColor Cyan

if (-not $GatewayIp) {
  try {
    $cfg = Get-NetIPConfiguration |
      Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq "Up" } |
      Select-Object -First 1
    if ($cfg) { $GatewayIp = [string]$cfg.IPv4DefaultGateway.NextHop }
  } catch {}
}
if (-not $GatewayIp) { $GatewayIp = "192.168.0.1" }

Write-Host "Manager=$ManagerIp  Gateway=$GatewayIp"
Write-Host ""
Write-Host "-- Firewall profiles --"
Get-NetFirewallProfile | Format-Table Name, Enabled, DefaultInboundAction, DefaultOutboundAction -AutoSize

Write-Host "-- Probes --"
$pingGw = Test-Connection -ComputerName $GatewayIp -Count 1 -Quiet -ErrorAction SilentlyContinue
Write-Host "Gateway ICMP ($GatewayIp) reachable=$pingGw  (under quarantine expect False)"

try {
  $smb = Test-NetConnection -ComputerName $GatewayIp -Port 445 -WarningAction SilentlyContinue
  Write-Host "Gateway TCP/445 TcpTestSucceeded=$($smb.TcpTestSucceeded)  (under quarantine expect False)"
} catch {
  Write-Host "Gateway TCP/445 probe error (often OK under quarantine)"
}

try {
  $mgr = Test-NetConnection -ComputerName $ManagerIp -Port 1514 -WarningAction SilentlyContinue
  Write-Host "Manager TCP/1514 TcpTestSucceeded=$($mgr.TcpTestSucceeded)  (under quarantine expect True or at least agent still active)"
} catch {
  Write-Host "Manager TCP/1514 probe error"
}

Write-Host ""
Write-Host "-- Recent AR log (QUARANTINE/VERIFY) --"
$log = "${env:ProgramFiles(x86)}\ossec-agent\active-response\active-responses.log"
if (Test-Path -LiteralPath $log) {
  Get-Content -LiteralPath $log -Tail 40 |
    Where-Object { $_ -match "mssp-isolate-host|QUARANTINE|VERIFY" }
} else {
  Write-Host "Log not found: $log"
}

Write-Host ""
Write-Host "PASS if AFTER isolate: Outbound=Block on all profiles, QUARANTINE ACTIVE applied=true, gateway probes fail."
Write-Host "FAIL if: Outbound=Allow, or QUARANTINE FAILED applied=false."
