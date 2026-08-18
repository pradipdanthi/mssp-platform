# MSSP isolate watchdog -- re-assert containment while the marker file exists.
# Runs as SYSTEM. Malware running as SYSTEM can still undo this; a kernel EDR
# driver is the next product tier. This stops accidental lift, old auto-release
# scripts, and unsophisticated malware flipping the firewall back to Allow.
$ErrorActionPreference = "Continue"
$CancelFile = Join-Path $env:ProgramData "mssp-edr-isolate-cancel.flag"
$MarkerFile = Join-Path $env:ProgramData "mssp-edr-quarantine.active"
$SidecarFile = Join-Path $env:ProgramData "mssp-edr-ar\watchdog-disabled-outbound.json"
if (Test-Path -LiteralPath $CancelFile) { exit 0 }
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
  $stdout = $p.StandardOutput.ReadToEnd()
  $p.StandardError.ReadToEnd() | Out-Null
  $p.WaitForExit()
  return $stdout
}

function Test-MsspFirewallRule([string]$Name) {
  $out = Invoke-Netsh @("advfirewall", "firewall", "show", "rule", "name=$Name")
  if ([string]::IsNullOrWhiteSpace($out)) { return $false }
  if ($out -match "No rules match") { return $false }
  return ($out -match [regex]::Escape($Name))
}

function Ensure-MsspFirewallRule([string]$Name, [string[]]$AddArgs) {
  if (Test-MsspFirewallRule $Name) { return }
  Invoke-Netsh $AddArgs | Out-Null
}

function Save-WatchdogDisabledOutbound([string[]]$NewNames) {
  $names = @($NewNames | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) })
  if ($names.Count -eq 0) { return }
  $dir = Split-Path $SidecarFile -Parent
  if (-not (Test-Path -LiteralPath $dir)) {
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
  }
  $existing = @()
  if (Test-Path -LiteralPath $SidecarFile) {
    try { $existing = @((Get-Content -LiteralPath $SidecarFile -Raw | ConvertFrom-Json)) } catch {}
  }
  $merged = @($existing + $names | Select-Object -Unique)
  try {
    ($merged | ConvertTo-Json -Compress) | Set-Content -LiteralPath $SidecarFile -Encoding ASCII
  } catch {}
}

try {
  Set-NetFirewallProfile -Profile Domain, Private, Public `
    -DefaultInboundAction Block -DefaultOutboundAction Block -Enabled True -ErrorAction Stop | Out-Null
} catch {
  foreach ($profile in @("domainprofile", "privateprofile", "publicprofile")) {
    Invoke-Netsh @("advfirewall", "set", $profile, "firewallpolicy", "blockinbound,blockoutbound")
  }
}

$disabledNow = @()
try {
  $sw = [Diagnostics.Stopwatch]::StartNew()
  foreach ($rule in @(Get-NetFirewallRule -Direction Outbound -Action Allow -Enabled True -ErrorAction SilentlyContinue)) {
    if ($sw.Elapsed.TotalSeconds -gt 12) { break }
    $n = [string]$rule.Name
    $d = [string]$rule.DisplayName
    if ($n -like "MSSP_*" -or $d -like "MSSP_*") { continue }
    try {
      Disable-NetFirewallRule -Name $n -ErrorAction SilentlyContinue
      $disabledNow += $n
    } catch {}
  }
} catch {}
Save-WatchdogDisabledOutbound -NewNames $disabledNow

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
  $args = @("advfirewall", "firewall", "add", "rule", "name=$($spec.Name)", "dir=$($spec.Dir)", "action=allow", "enable=yes", "profile=any") + $spec.Extra
  Ensure-MsspFirewallRule $spec.Name $args
}

if ((Test-Path -LiteralPath $CancelFile) -or -not (Test-Path -LiteralPath $MarkerFile)) { exit 0 }

foreach ($b in @(
  @{ Name = "MSSP_HOLD_BLOCK_RDP_IN"; Extra = @("dir=in", "protocol=tcp", "localport=3389") },
  @{ Name = "MSSP_HOLD_BLOCK_SMB_IN"; Extra = @("dir=in", "protocol=tcp", "localport=445") },
  @{ Name = "MSSP_HOLD_BLOCK_WINRM_IN"; Extra = @("dir=in", "protocol=tcp", "localport=5985,5986") }
)) {
  Ensure-MsspFirewallRule $b.Name (@("advfirewall", "firewall", "add", "rule", "name=$($b.Name)", "action=block", "enable=yes", "profile=any") + $b.Extra)
}

# Do NOT drop default routes here -- firewall default-deny is enough for quarantine,
# and removing 0.0.0.0/0 breaks internet restore if un-isolate misses route snapshot.

Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -match 'Start-Sleep' -and $_.CommandLine -match 'mssp-isolate-host' } |
  ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } catch {} }

exit 0
