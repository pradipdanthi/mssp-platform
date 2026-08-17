# MSSP isolate watchdog -- re-assert containment while the marker file exists.
# Runs as SYSTEM. Malware running as SYSTEM can still undo this; a kernel EDR
# driver is the next product tier. This stops accidental lift, old auto-release
# scripts, and unsophisticated malware flipping the firewall back to Allow.
$ErrorActionPreference = "Continue"
$MarkerFile = Join-Path $env:ProgramData "mssp-edr-quarantine.active"
if (-not (Test-Path -LiteralPath $MarkerFile)) { exit 0 }

$Manager = "192.168.0.226"
foreach ($confPath in @(
  "${env:ProgramFiles(x86)}\ossec-agent\ossec.conf",
  "$env:ProgramFiles\ossec-agent\ossec.conf"
)) {
  if (-not (Test-Path -LiteralPath $confPath)) { continue }
  try {
    [xml]$ox = Get-Content -LiteralPath $confPath
    $addr = [string]$ox.ossec_config.client.server.address
    if ($addr -match '^\d{1,3}(\.\d{1,3}){3}$') { $Manager = $addr }
  } catch {}
}

function Invoke-Netsh([string[]]$NetshArgs) {
  $info = New-Object System.Diagnostics.ProcessStartInfo
  $info.FileName = "netsh.exe"
  $info.Arguments = ($NetshArgs -join " ")
  $info.RedirectStandardOutput = $true
  $info.RedirectStandardError = $true
  $info.UseShellExecute = $false
  $info.CreateNoWindow = $true
  $p = [System.Diagnostics.Process]::Start($info)
  $p.StandardOutput.ReadToEnd() | Out-Null
  $p.StandardError.ReadToEnd() | Out-Null
  $p.WaitForExit()
}

try {
  Set-NetFirewallProfile -Profile Domain, Private, Public `
    -DefaultInboundAction Block -DefaultOutboundAction Block -Enabled True -ErrorAction Stop | Out-Null
} catch {
  foreach ($profile in @("domainprofile", "privateprofile", "publicprofile")) {
    Invoke-Netsh @("advfirewall", "set", $profile, "firewallpolicy", "blockinbound,blockoutbound")
  }
}

$rules = @(
  @{ Name = "MSSP_QUAR_ALLOW_WAZUH_OUT_1514"; Dir = "out"; Extra = @("protocol=tcp", "remoteip=$Manager", "remoteport=1514") },
  @{ Name = "MSSP_QUAR_ALLOW_WAZUH_OUT_1515"; Dir = "out"; Extra = @("protocol=tcp", "remoteip=$Manager", "remoteport=1515") },
  @{ Name = "MSSP_QUAR_ALLOW_WAZUH_IN_1514"; Dir = "in"; Extra = @("protocol=tcp", "remoteip=$Manager", "localport=1514") },
  @{ Name = "MSSP_QUAR_ALLOW_WAZUH_IN_1515"; Dir = "in"; Extra = @("protocol=tcp", "remoteip=$Manager", "localport=1515") },
  @{ Name = "MSSP_QUAR_ALLOW_WAZUH_OUT_UDP1514"; Dir = "out"; Extra = @("protocol=udp", "remoteip=$Manager", "remoteport=1514") },
  @{ Name = "MSSP_QUAR_ALLOW_DHCP"; Dir = "out"; Extra = @("protocol=udp", "remoteport=67,68") },
  @{ Name = "MSSP_QUAR_ALLOW_LOOPBACK_OUT"; Dir = "out"; Extra = @("remoteip=127.0.0.1") },
  @{ Name = "MSSP_QUAR_ALLOW_LOOPBACK_IN"; Dir = "in"; Extra = @("remoteip=127.0.0.1") }
)
foreach ($spec in $rules) {
  Invoke-Netsh @("advfirewall", "firewall", "delete", "rule", "name=$($spec.Name)")
  $args = @("advfirewall", "firewall", "add", "rule", "name=$($spec.Name)", "dir=$($spec.Dir)", "action=allow", "enable=yes", "profile=any") + $spec.Extra
  Invoke-Netsh $args
}

foreach ($b in @(
  @{ Name = "MSSP_HOLD_BLOCK_RDP_IN"; Extra = @("dir=in", "protocol=tcp", "localport=3389") },
  @{ Name = "MSSP_HOLD_BLOCK_SMB_IN"; Extra = @("dir=in", "protocol=tcp", "localport=445") },
  @{ Name = "MSSP_HOLD_BLOCK_WINRM_IN"; Extra = @("dir=in", "protocol=tcp", "localport=5985,5986") }
)) {
  Invoke-Netsh @("advfirewall", "firewall", "delete", "rule", "name=$($b.Name)")
  Invoke-Netsh (@("advfirewall", "firewall", "add", "rule", "name=$($b.Name)", "action=block", "enable=yes", "profile=any") + $b.Extra)
}

try {
  Get-NetRoute -AddressFamily IPv4 -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue |
    Remove-NetRoute -Confirm:$false -ErrorAction SilentlyContinue
} catch {}

Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -match 'Start-Sleep' -and $_.CommandLine -match 'mssp-isolate-host' } |
  ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } catch {} }

exit 0
