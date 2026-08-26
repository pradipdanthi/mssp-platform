# MSSP Windows Active Response -- HOST NETWORK QUARANTINE (EDR-style)
#
# Industry meaning of "isolate host" (MDR/XDR/PDR containment):
#   Place the endpoint in NETWORK QUARANTINE -- default DENY for all IP traffic
#   (TCP/UDP/ICMP/other), both inbound and outbound, except a tight allow-list
#   required for SOC control-plane continuity.
#
# This is NOT "block ping". ICMP is only one protocol among many. Quarantine
# must stop lateral movement (SMB/RDP/WinRM), C2 egress (HTTP/S, DNS tunneling
# to arbitrary resolvers), and data exfil -- while preserving agent<->Manager
# connectivity so analysts can still observe, unisolate, kill, or collect.
#
# Allow-list (minimal MSSP):
#   - Wazuh Manager IP (bi-directional, all protocols to that host)
#   - Loopback
#   - DHCP client (UDP 67/68) so the lease does not expire mid-incident
#
# Explicitly NOT allow-listed: LAN gateway, other endpoints, Internet, AD/SMB
# unless product policy later adds them as optional "business continuity" pins.
#
# Verification (logged; never claim success on dispatch alone):
#   - DefaultOutboundAction = Block on Domain/Private/Public
#   - Manager allow rule present
#   - Best-effort: Test-NetConnection to gateway should fail; Manager path OK
#
$ErrorActionPreference = "Continue"
$LogCandidates = @(
  "${env:ProgramFiles(x86)}\ossec-agent\active-response\active-responses.log",
  "$env:ProgramFiles\ossec-agent\active-response\active-responses.log"
)
$Log = $LogCandidates | Where-Object { Test-Path (Split-Path $_ -Parent) } | Select-Object -First 1
if (-not $Log) { $Log = $LogCandidates[0] }

$Manager = "192.168.0.211"
$ControlPlane = "192.168.0.201"
$StateFile = Join-Path $env:ProgramData "mssp-edr-isolate-state.json"
$MarkerFile = Join-Path $env:ProgramData "mssp-edr-quarantine.active"
$CancelFile = Join-Path $env:ProgramData "mssp-edr-isolate-cancel.flag"
$CallbackUrl = ""
$CallbackKey = ""
$envFile = Join-Path $PSScriptRoot "mssp-ar.env"
if (Test-Path -LiteralPath $envFile) {
  Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match '^\s*WAZUH_MANAGER_IP\s*=\s*(.+)\s*$') {
      $Manager = $Matches[1].Trim()
    }
    if ($_ -match '^\s*MSSP_CONTROL_PLANE_IP\s*=\s*(.+)\s*$') {
      $ControlPlane = $Matches[1].Trim()
    }
    if ($_ -match '^\s*MSSP_CALLBACK_URL\s*=\s*(.+)\s*$') {
      $CallbackUrl = $Matches[1].Trim()
    }
    if ($_ -match '^\s*MSSP_CALLBACK_KEY\s*=\s*(.+)\s*$') {
      $CallbackKey = $Matches[1].Trim()
    }
  }
}
# Fallback: Manager-shared callback material (auto-sync may not have written bin env yet).
if (-not $CallbackKey -or -not $CallbackUrl) {
  foreach ($sharedRoot in @(
    "${env:ProgramFiles(x86)}\ossec-agent\shared",
    "$env:ProgramFiles\ossec-agent\shared"
  )) {
    if (-not (Test-Path -LiteralPath $sharedRoot)) { continue }
    $def = Join-Path $sharedRoot "mssp-ar.env.defaults"
    if (Test-Path -LiteralPath $def) {
      Get-Content -LiteralPath $def | ForEach-Object {
        if (-not $CallbackUrl -and $_ -match '^\s*MSSP_CALLBACK_URL\s*=\s*(.+)\s*$') {
          $CallbackUrl = $Matches[1].Trim()
        }
        if (-not $CallbackKey -and $_ -match '^\s*MSSP_CALLBACK_KEY\s*=\s*(.+)\s*$') {
          $CallbackKey = $Matches[1].Trim()
        }
      }
    }
    if (-not $CallbackKey) {
      $kf = Join-Path $sharedRoot "mssp-callback.key"
      if (Test-Path -LiteralPath $kf) {
        $CallbackKey = (Get-Content -LiteralPath $kf -Raw).Trim()
      }
    }
  }
}
# Prefer callback URL host when set (KB-091: quarantine must still reach control plane).
# Hostname DNS resolve is deferred until Write-ArLog exists (see Resolve-MsspCallbackAllowIps).
$CallbackAllowIps = @()
if ($CallbackUrl) {
  try {
    $cbHost = ([Uri]$CallbackUrl).Host
    if ($cbHost -and $cbHost -match '^\d{1,3}(\.\d{1,3}){3}$') {
      $ControlPlane = $cbHost
      $CallbackAllowIps += $cbHost
    }
  } catch {  }
}

# Appliance-local Manager IP from the agent config when mssp-ar.env was never installed.
if ($Manager -eq "192.168.0.211") {
  foreach ($confPath in @(
    "${env:ProgramFiles(x86)}\ossec-agent\ossec.conf",
    "$env:ProgramFiles\ossec-agent\ossec.conf"
  )) {
    if (-not (Test-Path -LiteralPath $confPath)) { continue }
    try {
      [xml]$ox = Get-Content -LiteralPath $confPath
      $addr = [string]$ox.ossec_config.client.server.address
      if ($addr -match '^\d{1,3}(\.\d{1,3}){3}$') {
        $Manager = $addr
      }
    } catch {}
  }
}

function Test-MsspUnisolateRequested {
  return (Test-Path -LiteralPath $CancelFile)
}

function Write-ArLog([string]$Message) {
  $ts = (Get-Date).ToUniversalTime().ToString("yyyy/MM/dd HH:mm:ss")
  $line = "$ts mssp-isolate-host: $Message`r`n"
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($line)
  foreach ($path in @($Log, (Join-Path $env:ProgramData "mssp-edr-ar\isolate-debug.log"))) {
    try {
      $dir = Split-Path $path -Parent
      if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
      }
      $fs = [System.IO.File]::Open(
        $path,
        [System.IO.FileMode]::Append,
        [System.IO.FileAccess]::Write,
        [System.IO.FileShare]::ReadWrite
      )
      try { $fs.Write($bytes, 0, $bytes.Length) } finally { $fs.Dispose() }
    } catch {}
  }
}

function Resolve-MsspCallbackAllowIps {
  if (-not $CallbackUrl) { return }
  try {
    $cbHost = ([Uri]$CallbackUrl).Host
  } catch { return }
  if (-not $cbHost) { return }
  if ($cbHost -match '^\d{1,3}(\.\d{1,3}){3}$') { return }
  try {
    $resolved = [System.Net.Dns]::GetHostAddresses($cbHost) |
      Where-Object { $_.AddressFamily -eq 'InterNetwork' } |
      ForEach-Object { $_.IPAddressToString }
    foreach ($ip in $resolved) {
      if ($script:CallbackAllowIps -notcontains $ip) { $script:CallbackAllowIps += $ip }
    }
    Write-ArLog "callback host=$cbHost resolved=$($script:CallbackAllowIps -join ',')"
  } catch {
    Write-ArLog "WARN callback DNS resolve failed for $cbHost : $($_.Exception.Message)"
  }
}

function Send-MsspEdrCallback {
  param(
    [string]$ExecutionId,
    [string]$Status,
    [string]$Message,
    [bool]$Applied,
    [bool]$Released = $false,
    [string]$AgentId = ""
  )
  if (-not $ExecutionId) {
    Write-ArLog "CALLBACK skip: no execution_id"
    return
  }
  if (-not $CallbackUrl) {
    Write-ArLog "CALLBACK skip: MSSP_CALLBACK_URL not set in mssp-ar.env"
    return
  }
  $bodyObj = @{
    execution_id = $ExecutionId
    status       = $Status
    message      = $Message
    agent_id     = $AgentId
    applied      = $Applied
    released     = $Released
  }
  $json = $bodyObj | ConvertTo-Json -Compress
  try {
    $headers = @{}
    if ($CallbackKey) {
      $headers["X-SOC-Sync-Key"] = $CallbackKey
      $headers["X-EDR-Callback-Key"] = $CallbackKey
    }
    Invoke-RestMethod -Method Post -Uri $CallbackUrl -Body $json -ContentType "application/json" -Headers $headers -TimeoutSec 15 | Out-Null
    Write-ArLog "CALLBACK ok status=$Status applied=$Applied released=$Released exec=$ExecutionId"
  } catch {
    Write-ArLog "CALLBACK failed: $($_.Exception.Message)"
  }
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
  $stderr = $p.StandardError.ReadToEnd()
  $p.WaitForExit()
  return @{ ExitCode = $p.ExitCode; StdOut = $stdout; StdErr = $stderr }
}

function Clear-MsspAllowRules {
  foreach ($name in @(
    "MSSP_QUAR_ALLOW_MANAGER_OUT",
    "MSSP_QUAR_ALLOW_MANAGER_IN",
    "MSSP_QUAR_ALLOW_CTRLPLANE_OUT",
    "MSSP_QUAR_ALLOW_CTRLPLANE_IN",
    "MSSP_QUAR_ALLOW_WAZUH_OUT_1514",
    "MSSP_QUAR_ALLOW_WAZUH_OUT_1515",
    "MSSP_QUAR_ALLOW_WAZUH_IN_1514",
    "MSSP_QUAR_ALLOW_WAZUH_IN_1515",
    "MSSP_QUAR_ALLOW_WAZUH_OUT_UDP1514",
    "MSSP_QUAR_ALLOW_DHCP",
    "MSSP_QUAR_ALLOW_DNS_UDP",
    "MSSP_QUAR_ALLOW_DNS_TCP",
    "MSSP_QUAR_ALLOW_LOOPBACK_OUT",
    "MSSP_QUAR_ALLOW_LOOPBACK_IN",
    "MSSP_QUAR_ALLOW_CALLBACK_OUT_1",
    "MSSP_QUAR_ALLOW_CALLBACK_OUT_2",
    "MSSP_QUAR_ALLOW_CALLBACK_OUT_3",
    "MSSP_QUAR_ALLOW_CALLBACK_OUT_4",
    "MSSP_QUAR_ALLOW_CALLBACK_OUT_5",
    "MSSP_QUAR_ALLOW_CALLBACK_OUT_6",
    "MSSP_QUAR_ALLOW_CALLBACK_OUT_7",
    "MSSP_QUAR_ALLOW_CALLBACK_OUT_8",
    "MSSP_QUAR_BLOCK_RDP_IN",
    "MSSP_QUAR_BLOCK_RDP_OUT",
    "MSSP_QUAR_BLOCK_SMB_IN",
    "MSSP_QUAR_BLOCK_SMB_OUT",
    "MSSP_QUAR_BLOCK_WINRM_IN",
    "MSSP_QUAR_BLOCK_RPC_IN",
    "MSSP_QUAR_BLOCK_SSH_IN",
    "MSSP_QUAR_BLOCK_SSH_OUT",
    "MSSP_QUAR_BLOCK_ICMP_IN",
    "MSSP_QUAR_BLOCK_ICMP_OUT",
    # legacy names from earlier iterations
    "MSSP_ISOLATE_ALLOW_MANAGER_OUT",
    "MSSP_ISOLATE_ALLOW_MANAGER_IN",
    "MSSP_ISOLATE_ALLOW_DNS_UDP",
    "MSSP_ISOLATE_ALLOW_DNS_TCP",
    "MSSP_ISOLATE_ALLOW_DHCP",
    "MSSP_ISOLATE_ALLOW_LOOPBACK_OUT",
    "MSSP_ISOLATE_ALLOW_LOOPBACK_IN",
    "MSSP_ISOLATE_BLOCK_ICMP_OUT",
    "MSSP_ISOLATE_BLOCK_OUT",
    "MSSP_ISOLATE_BLOCK_IN",
    "MSSP_HOLD_BLOCK_RDP_IN",
    "MSSP_HOLD_BLOCK_RDP_OUT",
    "MSSP_HOLD_BLOCK_SMB_IN",
    "MSSP_HOLD_BLOCK_WINRM_IN",
    "MSSP_HOLD_BLOCK_ICMP_IN",
    "MSSP_HOLD_BLOCK_ICMP_OUT",
    "MSSP_RDP_RESTORE_IN"
  )) {
    [void](Invoke-Netsh @("advfirewall", "firewall", "delete", "rule", "name=$name"))
  }
}

$Script:MsspLateralFirewallGroups = @(
  "Remote Desktop",
  "Remote Assistance",
  "File and Printer Sharing",
  "Windows Remote Management",
  "World Wide Web Services (HTTP)",
  "Secure World Wide Web Services (HTTPS)"
)

function Get-MsspRemoteAccessState {
  $ra = [ordered]@{
    fDenyTSConnections   = $null
    term_service_start   = $null
    term_service_running = $null
  }
  try {
    $v = (Get-ItemProperty -Path "HKLM:\System\CurrentControlSet\Control\Terminal Server" `
      -Name fDenyTSConnections -ErrorAction Stop).fDenyTSConnections
    $ra.fDenyTSConnections = [int]$v
  } catch {}
  try {
    $svc = Get-Service -Name TermService -ErrorAction Stop
    $ra.term_service_start = [string]$svc.StartType
    $ra.term_service_running = ($svc.Status -eq "Running")
  } catch {}
  return $ra
}

function Restore-MsspRemoteAccessState([object]$Saved) {
  if (-not $Saved) { return }
  $deny = $null
  try { $deny = [int]$Saved.fDenyTSConnections } catch { $deny = $null }
  if ($null -ne $deny) {
    try {
      Set-ItemProperty -Path "HKLM:\System\CurrentControlSet\Control\Terminal Server" `
        -Name fDenyTSConnections -Value $deny -Type DWord -Force -ErrorAction Stop
      Write-ArLog "restore fDenyTSConnections=$deny"
    } catch {
      Write-ArLog "WARN restore fDenyTSConnections: $($_.Exception.Message)"
    }
  }
  $start = $null
  try { $start = [string]$Saved.term_service_start } catch { $start = $null }
  if ($start) {
    try {
      Set-Service -Name TermService -StartupType $start -ErrorAction Stop
      Write-ArLog "restore TermService StartupType=$start"
    } catch {
      Write-ArLog "WARN restore TermService start: $($_.Exception.Message)"
    }
  }
  $wasRunning = $false
  try { $wasRunning = [bool]$Saved.term_service_running } catch { $wasRunning = $false }
  if ($wasRunning) {
    try {
      Start-Service -Name TermService -ErrorAction Stop
      Write-ArLog "restore TermService started"
    } catch {
      Write-ArLog "WARN start TermService: $($_.Exception.Message)"
    }
  }
}

function Restore-MsspOutboundAllows([object]$SavedNames, [int]$MaxSeconds = 8) {
  if (-not $SavedNames) { return @() }
  $sw = [Diagnostics.Stopwatch]::StartNew()
  $count = 0
  foreach ($name in @($SavedNames)) {
    if ($sw.Elapsed.TotalSeconds -gt $MaxSeconds) { break }
    $n = [string]$name
    if (-not $n) { continue }
    try {
      Enable-NetFirewallRule -Name $n -ErrorAction Stop
      $count += 1
    } catch {
      Write-ArLog "WARN enable outbound allow $n : $($_.Exception.Message)"
    }
  }
  $remaining = @($SavedNames | Select-Object -Skip $count)
  Write-ArLog "restored outbound allow rules count=$count remaining=$($remaining.Count) elapsed=$([int]$sw.Elapsed.TotalSeconds)s"
  return @($remaining)
}

function Start-MsspOutboundAllowCompletion([object]$RuleNames) {
  $names = @($RuleNames | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) })
  if ($names.Count -eq 0) { return }
  $dir = Join-Path $env:ProgramData "mssp-edr-ar"
  New-Item -ItemType Directory -Path $dir -Force | Out-Null
  $payload = Join-Path $dir "outbound-complete.json"
  try {
    (@($names) | ConvertTo-Json -Compress) | Set-Content -LiteralPath $payload -Encoding ASCII
  } catch {
    Write-ArLog "WARN outbound completion payload: $($_.Exception.Message)"
    return
  }
  $ps64 = Join-Path $env:SystemRoot "sysnative\WindowsPowerShell\v1.0\powershell.exe"
  if (-not (Test-Path -LiteralPath $ps64)) {
    $ps64 = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
  }
  $script = $PSCommandPath
  if (-not $script) { $script = Join-Path $PSScriptRoot "mssp-isolate-host.ps1" }
  try {
    Start-Process -FilePath $ps64 -ArgumentList @(
      "-NoProfile", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass",
      "-File", $script, "complete-outbound", $payload
    ) -WindowStyle Hidden | Out-Null
    Write-ArLog "outbound allow completion scheduled count=$($names.Count)"
  } catch {
    Write-ArLog "WARN outbound completion start: $($_.Exception.Message)"
  }
}

function Get-MsspConfiguredGatewaySnapshot {
  $saved = @()
  try {
    foreach ($cfg in @(Get-NetIPConfiguration -ErrorAction SilentlyContinue)) {
      if (-not $cfg -or -not $cfg.NetAdapter -or $cfg.NetAdapter.Status -ne "Up") { continue }
      $nextHop = $null
      try { $nextHop = [string]$cfg.IPv4DefaultGateway.NextHop } catch { $nextHop = $null }
      if (-not $nextHop) { continue }
      $saved += [ordered]@{
        ifIndex = [int]$cfg.InterfaceIndex
        nextHop = $nextHop
        metric  = 0
        source  = "configured"
      }
    }
  } catch {
    Write-ArLog "WARN snapshot configured gateway: $($_.Exception.Message)"
  }
  return @($saved)
}

function Get-MsspDefaultRoutesSnapshot {
  $saved = @()
  try {
    foreach ($rt in @(Get-NetRoute -AddressFamily IPv4 -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue)) {
      $saved += [ordered]@{
        ifIndex = [int]$rt.InterfaceIndex
        nextHop = [string]$rt.NextHop
        metric  = [int]$rt.RouteMetric
        source  = "route"
      }
    }
  } catch {
    Write-ArLog "WARN snapshot default routes: $($_.Exception.Message)"
  }
  foreach ($cfgGw in @(Get-MsspConfiguredGatewaySnapshot)) {
    $exists = $false
    foreach ($rt in $saved) {
      if ([int]$rt.ifIndex -eq [int]$cfgGw.ifIndex -and [string]$rt.nextHop -eq [string]$cfgGw.nextHop) {
        $exists = $true
        break
      }
    }
    if (-not $exists) { $saved += $cfgGw }
  }
  return @($saved)
}

function Save-MsspIsolateState([object]$State) {
  try {
    $dir = Split-Path $StateFile -Parent
    if (-not (Test-Path -LiteralPath $dir)) {
      New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    ($State | ConvertTo-Json -Compress -Depth 8) | Set-Content -LiteralPath $StateFile -Encoding ASCII
  } catch {
    Write-ArLog "WARN save isolate state: $($_.Exception.Message)"
  }
}

function Read-MsspIsolateState {
  if (-not (Test-Path -LiteralPath $StateFile)) { return $null }
  try {
    return Get-Content -LiteralPath $StateFile -Raw | ConvertFrom-Json
  } catch {
    Write-ArLog "WARN read isolate state: $($_.Exception.Message)"
    return $null
  }
}

function Restore-MsspFirewallProfilesFromState([object]$State) {
  if (-not $State) {
    Set-FirewallOutboundAllowFast
    return
  }
  foreach ($pair in @(
    @{ Name = "Domain";  Prof = "domainprofile" },
    @{ Name = "Private"; Prof = "privateprofile" },
    @{ Name = "Public";  Prof = "publicprofile" }
  )) {
    $key = $pair.Name.ToLowerInvariant()
    $inA = $null; $outA = $null; $en = $true
    try { $inA = [string]$State."${key}_in" } catch {}
    try { $outA = [string]$State."${key}_out" } catch {}
    try { $en = [bool]$State."${key}_enabled" } catch {}
    if (-not $inA) { $inA = "Block" }
    if (-not $outA -or $outA -eq "Block") { $outA = "Allow" }
    $inPart = if ($inA -eq "Block") { "blockinbound" } else { "allowinbound" }
    $outPart = if ($outA -eq "Block") { "blockoutbound" } else { "allowoutbound" }
    $r = Invoke-Netsh @("advfirewall", "set", $pair.Prof, "firewallpolicy", "$inPart,$outPart")
    Write-ArLog "restore profile $($pair.Prof) $inPart,$outPart rc=$($r.ExitCode)"
    if (-not $en) {
      [void](Invoke-Netsh @("advfirewall", "set", $pair.Prof, "state", "off"))
    }
  }
}

function Restore-MsspOutboundAllowsFromSidecar([int]$MaxSeconds = 8) {
  $sidecar = Join-Path $env:ProgramData "mssp-edr-ar\watchdog-disabled-outbound.json"
  $names = @()
  if (Test-Path -LiteralPath $sidecar) {
    try {
      $names = @((Get-Content -LiteralPath $sidecar -Raw | ConvertFrom-Json))
    } catch {}
  }
  $remaining = @()
  if ($names.Count -gt 0) {
    $remaining = @(Restore-MsspOutboundAllows -SavedNames $names -MaxSeconds $MaxSeconds)
  }
  foreach ($g in @("Core Networking", "World Wide Web Services (HTTP)", "Secure World Wide Web Services (HTTPS)")) {
    [void](Invoke-Netsh @("advfirewall", "firewall", "set", "rule", "group=$g", "new", "enable=yes"))
  }
  if ($remaining.Count -eq 0) {
    Remove-Item -LiteralPath $sidecar -Force -ErrorAction SilentlyContinue
  } else {
    try {
      (@($remaining) | ConvertTo-Json -Compress) | Set-Content -LiteralPath $sidecar -Encoding ASCII
    } catch {}
  }
  return @($remaining)
}

function Test-MsspReleaseEffect {
  $ok = $true
  try {
    $blocked = @(Get-NetFirewallProfile -Profile Domain, Private, Public -ErrorAction Stop |
      Where-Object { $_.DefaultOutboundAction -eq "Block" }).Count
    if ($blocked -gt 0) {
      Write-ArLog "VERIFY release outbound still Block on $blocked/3 profiles"
      $ok = $false
    }
  } catch {
    Write-ArLog "VERIFY release profile check failed: $($_.Exception.Message)"
  }
  try {
    $routes = @(Get-NetRoute -AddressFamily IPv4 -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue)
    if ($routes.Count -eq 0) {
      Write-ArLog "VERIFY release no default route"
      $ok = $false
    }
  } catch {}
  Write-ArLog "VERIFY release effective=$ok"
  return $ok
}

function Stop-MsspWatchdogProcesses {
  Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
    Where-Object {
      $cl = [string]$_.CommandLine
      ($cl -match 'Watch-MsspQuarantine') -or
      ($cl -match 'complete-outbound') -or
      ($cl -match 'deferred-repair' -and $cl -match 'mssp-isolate-host')
    } |
    ForEach-Object {
      try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } catch {}
    }
}

function Restore-AllNonMsspOutboundAllows([int]$MaxSeconds = 30) {
  $sw = [Diagnostics.Stopwatch]::StartNew()
  $count = 0
  try {
    foreach ($rule in @(Get-NetFirewallRule -Direction Outbound -Action Allow -Enabled False -ErrorAction SilentlyContinue)) {
      if ($sw.Elapsed.TotalSeconds -gt $MaxSeconds) { break }
      $n = [string]$rule.Name
      $d = [string]$rule.DisplayName
      if ($n -like "MSSP_*" -or $d -like "MSSP_*") { continue }
      try {
        Enable-NetFirewallRule -Name $n -ErrorAction Stop
        $count += 1
      } catch {}
    }
  } catch {
    Write-ArLog "bulk outbound allow restore: $($_.Exception.Message)"
  }
  Write-ArLog "bulk enabled outbound allow rules count=$count elapsed=$([int]$sw.Elapsed.TotalSeconds)s"
  return $count
}

function Invoke-MsspUnisolate([string]$ExecutionId = "", [switch]$ForceFullRestore) {
  # Single end-to-end restore: everything isolate changed must be reversed here.
  Write-ArLog "UNISOLATE begin exec=$ExecutionId full=$ForceFullRestore"
  $env:MSSP_SKIP_SCRIPT_SYNC = "1"
  try { "cancelled" | Set-Content -LiteralPath $CancelFile -Encoding ASCII } catch {}

  # Stop watchdog FIRST and drop marker immediately so it cannot re-block outbound mid-restore.
  Stop-MsspQuarantineWatchdog
  Stop-MsspWatchdogProcesses
  Stop-StaleAutoRelease
  Remove-Item -LiteralPath $MarkerFile -Force -ErrorAction SilentlyContinue

  $state = Read-MsspIsolateState
  if ($state -and -not $ExecutionId) {
    try { $ExecutionId = [string]$state.execution_id } catch { $ExecutionId = "" }
  }

  $routes = $null
  if ($state) { try { $routes = @($state.default_routes) } catch { $routes = $null } }

  # 1) Firewall profiles -> outbound Allow (internet path)
  Restore-MsspFirewallProfilesFromState -State $state

  # 2) Remove every MSSP quarantine rule (including outbound blocks)
  Clear-MsspQuarantineRulesFast
  Clear-MsspAllowRules
  [void](Invoke-Netsh @("advfirewall", "firewall", "delete", "rule", "name=MSSP_RDP_RESTORE_IN"))

  # 3) Full internet repair: routes + core groups + outbound Allow on all profiles
  Repair-MsspInternetConnectivity -SavedRoutes $routes

  # 4) Restore lateral firewall groups disabled during isolate
  if ($state -and $state.disabled_allow_rules) {
    Restore-MsspLateralAllowRules -SavedRules $state.disabled_allow_rules
  } else {
    Repair-MsspLateralAccess
  }

  # 5) Re-enable outbound allow rules the watchdog disabled
  $outboundMax = if ($ForceFullRestore) { 120 } else { 8 }
  $pendingOutbound = @()
  if ($state -and $state.disabled_outbound_allows) {
    $pendingOutbound = @(Restore-MsspOutboundAllows -SavedNames $state.disabled_outbound_allows -MaxSeconds $outboundMax)
  }
  $pendingOutbound += @(Restore-MsspOutboundAllowsFromSidecar -MaxSeconds $outboundMax)
  if ($ForceFullRestore) {
    [void](Restore-AllNonMsspOutboundAllows -MaxSeconds 90)
    $pendingOutbound = @()
  } elseif ($pendingOutbound.Count -gt 0) {
    Start-MsspOutboundAllowCompletion -RuleNames @($pendingOutbound | Select-Object -Unique)
    $pendingOutbound = @()
  }

  # 6) Restore RDP / TermService / registry exactly as before isolate
  if ($state -and $state.remote_access) {
    Restore-MsspRemoteAccessState -Saved $state.remote_access
  }
  Repair-MsspRdpAccessExplicit -SavedRemoteAccess $(if ($state) { $state.remote_access } else { $null })

  # 7) ICMP + state cleanup
  Repair-MsspEchoRequestRules
  Remove-Item -LiteralPath $StateFile -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $CancelFile -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath (Join-Path $env:ProgramData "mssp-edr-ar\watchdog-disabled-outbound.json") -Force -ErrorAction SilentlyContinue

  $released = Test-MsspReleaseEffect
  if ($ExecutionId) {
    $msg = if ($released) { "QUARANTINE RELEASED applied=true" } else { "QUARANTINE RELEASED applied=false (verify on host)" }
    Send-MsspEdrCallback -ExecutionId $ExecutionId -Status $(if ($released) { "success" } else { "failed" }) `
      -Message $msg -Applied $released -Released $true
  }
  Write-ArLog "UNISOLATE complete released=$released exec=$ExecutionId"
  return $ExecutionId
}

function Repair-MsspDefaultRoutesFallback([object]$SavedRoutes) {
  if ($SavedRoutes) {
    try { Restore-DefaultRoutes -Saved $SavedRoutes } catch {}
  }
  try {
    $existing = @(Get-NetRoute -AddressFamily IPv4 -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue)
    if ($existing.Count -gt 0) {
      Write-ArLog "default route present count=$($existing.Count)"
      return
    }
  } catch {}
  Write-ArLog "default route missing; rediscovering gateway"
  $candidates = @()
  if ($SavedRoutes) {
    foreach ($item in @($SavedRoutes)) {
      if ($item -and [string]$item.nextHop) { $candidates += $item }
    }
  }
  foreach ($cfgGw in @(Get-MsspConfiguredGatewaySnapshot)) { $candidates += $cfgGw }
  try {
    foreach ($item in @($candidates)) {
      $ifIndex = 0; $nextHop = $null; $metric = 0
      try { $ifIndex = [int]$item.ifIndex } catch { continue }
      try { $nextHop = [string]$item.nextHop } catch { continue }
      try { $metric = [int]$item.metric } catch { $metric = 0 }
      if (-not $ifIndex -or -not $nextHop) { continue }
      try {
        $params = @{
          InterfaceIndex    = $ifIndex
          DestinationPrefix = "0.0.0.0/0"
          NextHop           = $nextHop
          ErrorAction       = "Stop"
        }
        if ($metric -gt 0) { $params["RouteMetric"] = $metric }
        New-NetRoute @params | Out-Null
        Write-ArLog "fallback default route if=$ifIndex gw=$nextHop source=$($item.source)"
        return
      } catch {
        Write-ArLog "WARN fallback route if=$ifIndex gw=$nextHop : $($_.Exception.Message)"
      }
    }
  } catch {
    Write-ArLog "WARN route discovery: $($_.Exception.Message)"
  }
  try {
    $null = & ipconfig.exe /renew 2>&1
    Write-ArLog "ipconfig /renew for DHCP route recovery"
  } catch {
    Write-ArLog "WARN ipconfig renew: $($_.Exception.Message)"
  }
  try {
    $existing = @(Get-NetRoute -AddressFamily IPv4 -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue)
    if ($existing.Count -gt 0) {
      Write-ArLog "default route restored after renew count=$($existing.Count)"
    }
  } catch {}
}

function Repair-MsspDnsConnectivity {
  foreach ($g in @("Core Networking")) {
    $r = Invoke-Netsh @("advfirewall", "firewall", "set", "rule", "group=$g", "new", "enable=yes")
    Write-ArLog "DNS repair group '$g' rc=$($r.ExitCode)"
  }
  foreach ($spec in @(
    @{ Name = "MSSP_DNS_RESTORE_UDP"; Proto = "udp" },
    @{ Name = "MSSP_DNS_RESTORE_TCP"; Proto = "tcp" }
  )) {
    [void](Invoke-Netsh @("advfirewall", "firewall", "delete", "rule", "name=$($spec.Name)"))
    $r = Invoke-Netsh @(
      "advfirewall", "firewall", "add", "rule", "name=$($spec.Name)",
      "dir=out", "action=allow", "protocol=$($spec.Proto)", "remoteport=53",
      "enable=yes", "profile=any"
    )
    Write-ArLog "DNS repair rule $($spec.Name) rc=$($r.ExitCode)"
  }
  try { Restart-Service -Name Dnscache -Force -ErrorAction SilentlyContinue } catch {}
  try { $null = & ipconfig.exe /flushdns 2>&1 } catch {}
  try { $null = & ipconfig.exe /registerdns 2>&1 } catch {}
  try {
    $needsDns = $true
    foreach ($row in @(Get-DnsClientServerAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue)) {
      if (@($row.ServerAddresses | Where-Object { $_ }).Count -gt 0) {
        $needsDns = $false
        break
      }
    }
    if ($needsDns) {
      $null = & ipconfig.exe /renew 2>&1
      Start-Sleep -Seconds 2
      $needsDns = $true
      foreach ($row in @(Get-DnsClientServerAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue)) {
        if (@($row.ServerAddresses | Where-Object { $_ }).Count -gt 0) {
          $needsDns = $false
          break
        }
      }
    }
    if ($needsDns) {
      $cfg = @(Get-NetIPConfiguration -ErrorAction SilentlyContinue |
        Where-Object { $_.NetAdapter -and $_.NetAdapter.Status -eq "Up" }) | Select-Object -First 1
      if ($cfg) {
        $servers = @()
        try {
          $gw = [string]$cfg.IPv4DefaultGateway.NextHop
          if ($gw) { $servers += $gw }
        } catch {}
        $servers += @("8.8.8.8", "8.8.4.4")
        Set-DnsClientServerAddress -InterfaceIndex $cfg.InterfaceIndex -ServerAddresses $servers -ErrorAction Stop
        Write-ArLog "DNS servers set fallback servers=$($servers -join ',')"
      }
    }
  } catch {
    Write-ArLog "WARN DNS server repair: $($_.Exception.Message)"
  }
}

function Repair-MsspInternetConnectivity([object]$SavedRoutes) {
  # Full network restore: firewall outbound + core groups + default gateway route + DNS.
  Set-FirewallOutboundAllowFast
  foreach ($g in @(
    "Core Networking",
    "Windows Remote Desktop",
    "World Wide Web Services (HTTP)",
    "Secure World Wide Web Services (HTTPS)",
    "File and Printer Sharing"
  )) {
    $r = Invoke-Netsh @("advfirewall", "firewall", "set", "rule", "group=$g", "new", "enable=yes")
    Write-ArLog "internet repair group '$g' rc=$($r.ExitCode)"
  }
  Repair-MsspDefaultRoutesFallback -SavedRoutes $SavedRoutes
  Repair-MsspDnsConnectivity
  Clear-MsspAllowRules
  Write-ArLog "internet connectivity repair complete"
}

function Repair-MsspRdpAccessExplicit([object]$SavedRemoteAccess) {
  # Netsh-only (Get-NetFirewallRule hangs 32-bit execd). Always re-enable RDP.
  [void](Invoke-Netsh @("advfirewall", "firewall", "set", "rule", "group=Remote Desktop", "new", "enable=yes"))
  [void](Invoke-Netsh @("advfirewall", "firewall", "set", "rule", "group=remote desktop", "new", "enable=yes"))
  [void](Invoke-Netsh @("advfirewall", "firewall", "delete", "rule", "name=MSSP_HOLD_BLOCK_RDP_IN"))
  [void](Invoke-Netsh @("advfirewall", "firewall", "delete", "rule", "name=MSSP_HOLD_BLOCK_RDP_OUT"))
  [void](Invoke-Netsh @("advfirewall", "firewall", "delete", "rule", "name=MSSP_QUAR_BLOCK_RDP_IN"))
  [void](Invoke-Netsh @("advfirewall", "firewall", "delete", "rule", "name=MSSP_QUAR_BLOCK_RDP_OUT"))
  [void](Invoke-Netsh @(
    "advfirewall", "firewall", "delete", "rule", "name=MSSP_RDP_RESTORE_IN"
  ))
  $r = Invoke-Netsh @(
    "advfirewall", "firewall", "add", "rule",
    "name=MSSP_RDP_RESTORE_IN", "dir=in", "action=allow",
    "protocol=tcp", "localport=3389", "enable=yes", "profile=any"
  )
  Write-ArLog "RDP repair explicit 3389 allow rc=$($r.ExitCode)"
  try {
    Set-ItemProperty -Path "HKLM:\System\CurrentControlSet\Control\Terminal Server" `
      -Name fDenyTSConnections -Value 0 -Type DWord -Force -ErrorAction Stop
    Write-ArLog "RDP repair fDenyTSConnections=0"
  } catch {
    Write-ArLog "WARN RDP registry: $($_.Exception.Message)"
  }
  try {
    $svc = Get-Service -Name TermService -ErrorAction SilentlyContinue
    if ($svc -and $svc.StartType -eq "Disabled") {
      Set-Service -Name TermService -StartupType Manual -ErrorAction SilentlyContinue
    }
    if ($svc -and $svc.Status -ne "Running") {
      Start-Service -Name TermService -WarningAction SilentlyContinue -ErrorAction Stop
      Write-ArLog "RDP repair TermService started"
    }
  } catch {
    Write-ArLog "WARN RDP TermService: $($_.Exception.Message)"
  }
}

function Repair-MsspLateralAccess {
  foreach ($g in $Script:MsspLateralFirewallGroups) {
    $r = Invoke-Netsh @("advfirewall", "firewall", "set", "rule", "group=$g", "new", "enable=yes")
    Write-ArLog "repair lateral group '$g' rc=$($r.ExitCode)"
  }
  try {
    $svc = Get-Service -Name TermService -ErrorAction SilentlyContinue
    if ($svc -and $svc.StartType -ne "Disabled" -and $svc.Status -ne "Running") {
      Start-Service -Name TermService -ErrorAction Stop
      Write-ArLog "repair TermService started"
    }
  } catch {
    Write-ArLog "WARN repair TermService: $($_.Exception.Message)"
  }
}

function Disable-NonMsspOutboundAllows {
  # DefaultOutboundAction=Block does NOT override existing Allow rules.
  # Chrome/Edge/TrueConf Allow rules are why internet stayed up while Isolated.
  # Timebox so 32-bit execd cannot hang; cap saved names so unisolate stays fast.
  $sw = [Diagnostics.Stopwatch]::StartNew()
  $disabled = 0
  $disabledNames = @()
  $maxSaved = 40
  try {
    $rules = @(Get-NetFirewallRule -Direction Outbound -Action Allow -Enabled True -ErrorAction Stop)
    foreach ($rule in $rules) {
      if ($sw.Elapsed.TotalSeconds -gt 12) {
        Write-ArLog "disable outbound allows timebox; watchdog will continue count=$disabled"
        break
      }
      if ($disabledNames.Count -ge $maxSaved) {
        Write-ArLog "disable outbound allows cap=$maxSaved (watchdog continues)"
        break
      }
      $n = [string]$rule.Name
      $d = [string]$rule.DisplayName
      if ($n -like "MSSP_*" -or $d -like "MSSP_*") { continue }
      try {
        Disable-NetFirewallRule -Name $n -ErrorAction Stop
        $disabled += 1
        $disabledNames += $n
      } catch {}
    }
  } catch {
    Write-ArLog "disable outbound allows: $($_.Exception.Message)"
  }
  Write-ArLog "disabled outbound allow rules count=$disabled elapsed=$([int]$sw.Elapsed.TotalSeconds)s"
  return @($disabledNames)
}

function Disable-MsspLateralAllowRules {
  # Do NOT call Get-NetFirewallRule (enumerating every rule hangs 32-bit execd).
  $saved = @()
  foreach ($g in $Script:MsspLateralFirewallGroups) {
    $r = Invoke-Netsh @("advfirewall", "firewall", "set", "rule", "group=$g", "new", "enable=no")
    Write-ArLog "disable group '$g' rc=$($r.ExitCode)"
    $saved += [ordered]@{ group = $g; was_enabled = $true }
  }
  return @($saved)
}

function Restore-MsspLateralAllowRules([object]$SavedRules) {
  if (-not $SavedRules) { return }
  foreach ($item in @($SavedRules)) {
    $group = $null
    try { $group = [string]$item.group } catch { $group = $null }
    if ($group) {
      $r = Invoke-Netsh @("advfirewall", "firewall", "set", "rule", "group=$group", "new", "enable=yes")
      Write-ArLog "restore group '$group' rc=$($r.ExitCode)"
      continue
    }
    $name = $null
    $wasEnabled = $true
    if ($item -is [string]) {
      $name = $item
      $wasEnabled = $true
    } else {
      try { $name = [string]$item.name } catch { $name = $null }
      try {
        if ($null -ne $item.was_enabled) { $wasEnabled = [bool]$item.was_enabled }
      } catch {}
    }
    if (-not $name) { continue }
    $enable = if ($wasEnabled) { "yes" } else { "no" }
    [void](Invoke-Netsh @("advfirewall", "firewall", "set", "rule", "name=$name", "new", "enable=$enable"))
    Write-ArLog "Restored rule name=$name enable=$enable"
  }
}

function Add-LateralBlockRules {
  # Block rules take precedence over Allow -- belt-and-suspenders for admin/lateral ports.
  $blocks = @(
    @{ Name = "MSSP_QUAR_BLOCK_RDP_IN"; Dir = "in"; Extra = @("protocol=tcp", "localport=3389") },
    @{ Name = "MSSP_QUAR_BLOCK_RDP_OUT"; Dir = "out"; Extra = @("protocol=tcp", "remoteport=3389") },
    @{ Name = "MSSP_QUAR_BLOCK_SMB_IN"; Dir = "in"; Extra = @("protocol=tcp", "localport=445") },
    @{ Name = "MSSP_QUAR_BLOCK_SMB_OUT"; Dir = "out"; Extra = @("protocol=tcp", "remoteport=445") },
    @{ Name = "MSSP_QUAR_BLOCK_WINRM_IN"; Dir = "in"; Extra = @("protocol=tcp", "localport=5985,5986") },
    @{ Name = "MSSP_QUAR_BLOCK_RPC_IN"; Dir = "in"; Extra = @("protocol=tcp", "localport=135") },
    @{ Name = "MSSP_QUAR_BLOCK_SSH_IN"; Dir = "in"; Extra = @("protocol=tcp", "localport=22") },
    @{ Name = "MSSP_QUAR_BLOCK_SSH_OUT"; Dir = "out"; Extra = @("protocol=tcp", "remoteport=22") },
    # Explicit ICMP blocks (in addition to profile default-deny) for complete containment.
    @{ Name = "MSSP_QUAR_BLOCK_ICMP_IN"; Dir = "in"; Extra = @("protocol=icmpv4:8,any") },
    @{ Name = "MSSP_QUAR_BLOCK_ICMP_OUT"; Dir = "out"; Extra = @("protocol=icmpv4:8,any") },
    # HOLD_* names are unknown to older auto-release scripts. They keep RDP/SMB
    # down even if a stale 120s sleeper deletes MSSP_QUAR_* and restores defaults.
    @{ Name = "MSSP_HOLD_BLOCK_RDP_IN"; Dir = "in"; Extra = @("protocol=tcp", "localport=3389") },
    @{ Name = "MSSP_HOLD_BLOCK_RDP_OUT"; Dir = "out"; Extra = @("protocol=tcp", "remoteport=3389") },
    @{ Name = "MSSP_HOLD_BLOCK_SMB_IN"; Dir = "in"; Extra = @("protocol=tcp", "localport=445") },
    @{ Name = "MSSP_HOLD_BLOCK_WINRM_IN"; Dir = "in"; Extra = @("protocol=tcp", "localport=5985,5986") },
    @{ Name = "MSSP_HOLD_BLOCK_ICMP_IN"; Dir = "in"; Extra = @("protocol=icmpv4:8,any") },
    @{ Name = "MSSP_HOLD_BLOCK_ICMP_OUT"; Dir = "out"; Extra = @("protocol=icmpv4:8,any") }
  )
  foreach ($b in $blocks) {
    $args = @(
      "advfirewall", "firewall", "add", "rule",
      "name=$($b.Name)", "dir=$($b.Dir)", "action=block",
      "enable=yes", "profile=any"
    ) + $b.Extra
    $r = Invoke-Netsh $args
    Write-ArLog "block $($b.Name) rc=$($r.ExitCode)"
  }
}

function Stop-InteractiveRemoteSessions {
  # Stateful firewall often leaves EXISTING RDP TCP sessions alive.
  # Drop RDP only — never reset console/local session (operator may be at the keyboard).
  Write-ArLog "Dropping interactive RDP sessions for containment (console left intact)"
  try {
    $sessions = & qwinsta 2>$null
    foreach ($line in $sessions) {
      # Match only rdp-tcp#N rows; ignore console / services.
      if ($line -match 'rdp-tcp#\d+\s+\S+\s+(\d+)') {
        $id = $Matches[1]
        if ($id -and $id -ne "0") {
          try {
            & rwinsta $id 2>$null
            Write-ArLog "reset RDP session id=$id"
          } catch {
            Write-ArLog "WARN reset session $id failed"
          }
        }
      }
    }
  } catch {
    Write-ArLog "WARN session reset: $($_.Exception.Message)"
  }
}

function Set-FirewallDefaultActions([string]$Inbound, [string]$Outbound) {
  $ok = $false
  try {
    Set-NetFirewallProfile -Profile Domain, Private, Public `
      -DefaultInboundAction $Inbound `
      -DefaultOutboundAction $Outbound `
      -Enabled True `
      -ErrorAction Stop | Out-Null
    $ok = $true
    Write-ArLog "QUARANTINE profile defaults inbound=$Inbound outbound=$Outbound OK"
  } catch {
    Write-ArLog "Set-NetFirewallProfile failed: $($_.Exception.Message)"
  }
  if (-not $ok) {
    $inPart = if ($Inbound -eq "Block") { "blockinbound" } else { "allowinbound" }
    $outPart = if ($Outbound -eq "Block") { "blockoutbound" } else { "allowoutbound" }
    $policy = "$inPart,$outPart"
    foreach ($profile in @("domainprofile", "privateprofile", "publicprofile")) {
      $r = Invoke-Netsh @("advfirewall", "set", $profile, "firewallpolicy", $policy)
      Write-ArLog "netsh set $profile $policy rc=$($r.ExitCode) err=$($r.StdErr.Trim())"
      if ($r.ExitCode -eq 0) { $ok = $true }
    }
  }
  return $ok
}

function Get-FirewallStateObject {
  # Full pre-quarantine snapshot so lift restores the host exactly.
  $state = [ordered]@{
    saved_at           = (Get-Date).ToUniversalTime().ToString("o")
    manager            = $Manager
    control_plane      = $ControlPlane
    execution_id       = ""
    domain_in          = "Block"; domain_out  = "Allow"; domain_enabled  = $true
    private_in         = "Block"; private_out = "Allow"; private_enabled = $true
    public_in          = "Block"; public_out  = "Allow"; public_enabled  = $true
    disabled_allow_rules = @()
  }
  try {
    foreach ($p in Get-NetFirewallProfile -Profile Domain, Private, Public -ErrorAction Stop) {
      $key = $p.Name.ToLowerInvariant()
      $state["${key}_in"] = [string]$p.DefaultInboundAction
      $state["${key}_out"] = [string]$p.DefaultOutboundAction
      $state["${key}_enabled"] = [bool]($p.Enabled -eq "True" -or $p.Enabled -eq $true)
    }
  } catch {
    Write-ArLog "Get-NetFirewallProfile failed: $($_.Exception.Message)"
  }
  return $state
}

function Test-QuarantineEffect {
  # Multi-signal verification -- not ICMP-only.
  $result = [ordered]@{
    profiles_outbound_block = $false
    manager_allow_rule      = $false
    gateway_probe_blocked   = $null
    notes                   = @()
  }
  try {
    $profiles = @(Get-NetFirewallProfile -Profile Domain, Private, Public -ErrorAction Stop)
    $blocked = @($profiles | Where-Object { $_.DefaultOutboundAction -eq "Block" }).Count
    $result.profiles_outbound_block = ($blocked -eq 3)
    $result.notes += "outbound_block_profiles=$blocked/3"
  } catch {
    $result.notes += "profile_read_failed=$($_.Exception.Message)"
  }

  $rules = Invoke-Netsh @("advfirewall", "firewall", "show", "rule", "name=MSSP_QUAR_ALLOW_WAZUH_OUT_1514")
  if ($rules.StdOut -match "MSSP_QUAR_ALLOW_WAZUH_OUT_1514" -and $rules.StdOut -notmatch "No rules match") {
    $result.manager_allow_rule = $true
  }

  # Do not probe the gateway here -- CIM/WMI probes can hang 32-bit execd.
  $result.gateway_probe_blocked = $null
  $result.notes += "gateway_probe_skipped"

  $effective = [bool]$result.profiles_outbound_block -and [bool]$result.manager_allow_rule
  Write-ArLog ("VERIFY effective=$effective " + ($result.notes -join "; "))
  return $effective
}

function Convert-ToMsspBool($Value, [bool]$Default = $true) {
  if ($null -eq $Value) { return $Default }
  if ($Value -is [bool]) { return $Value }
  $s = ([string]$Value).Trim().ToLowerInvariant()
  if ($s -in @("true", "1", "yes")) { return $true }
  if ($s -in @("false", "0", "no")) { return $false }
  return $Default
}

function Stop-StaleAutoRelease {
  Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'Start-Sleep' -and $_.CommandLine -match 'mssp-isolate-host' } |
    ForEach-Object {
      try {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop
        Write-ArLog "killed stale auto-release pid=$($_.ProcessId)"
      } catch {}
    }
}

function Install-MsspQuarantineWatchdog {
  if (Test-MsspUnisolateRequested) {
    Write-ArLog "watchdog skip: unisolate already requested"
    return
  }
  $dir = Join-Path $env:ProgramData "mssp-edr-ar"
  New-Item -ItemType Directory -Path $dir -Force | Out-Null
  $watchSrc = Join-Path $PSScriptRoot "Watch-MsspQuarantine.ps1"
  $watchDst = Join-Path $dir "Watch-MsspQuarantine.ps1"
  foreach ($candidate in @(
    $watchSrc,
    (Join-Path $PSScriptRoot "..\..\shared\Watch-MsspQuarantine.ps1")
  )) {
    if (Test-Path -LiteralPath $candidate) {
      Copy-Item -LiteralPath $candidate -Destination $watchDst -Force
      break
    }
  }
  if (-not (Test-Path -LiteralPath $watchDst)) {
    Write-ArLog "WARN watchdog script missing; containment will not re-assert"
    return
  }
  $tr = "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$watchDst`""
  schtasks.exe /Create /TN "MSSP-Quarantine-Watchdog" /SC MINUTE /MO 1 /RU SYSTEM /RL HIGHEST /TR $tr /F | Out-Null
  try {
    $task = Get-ScheduledTask -TaskName "MSSP-Quarantine-Watchdog" -ErrorAction Stop
    $trig = $task.Triggers | Select-Object -First 1
    if ($trig) {
      $trig.Repetition.Interval = "PT15S"
      $trig.Repetition.Duration = "P1D"
      Set-ScheduledTask -InputObject $task | Out-Null
    }
  } catch {}
  schtasks.exe /Run /TN "MSSP-Quarantine-Watchdog" | Out-Null
  Write-ArLog "watchdog installed (re-asserts Wazuh-only contain while marker exists)"
}

function Stop-MsspQuarantineWatchdog {
  schtasks.exe /End /TN "MSSP-Quarantine-Watchdog" 2>$null | Out-Null
  schtasks.exe /Delete /TN "MSSP-Quarantine-Watchdog" /F 2>$null | Out-Null
}

function Save-And-DropDefaultRoutes {
  $saved = @()
  try {
    foreach ($rt in @(Get-NetRoute -AddressFamily IPv4 -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue)) {
      $saved += [ordered]@{
        ifIndex  = [int]$rt.InterfaceIndex
        nextHop  = [string]$rt.NextHop
        metric   = [int]$rt.RouteMetric
      }
      try {
        Remove-NetRoute -InterfaceIndex $rt.InterfaceIndex -DestinationPrefix "0.0.0.0/0" -NextHop $rt.NextHop -Confirm:$false -ErrorAction Stop
        Write-ArLog "dropped default route if=$($rt.InterfaceIndex) gw=$($rt.NextHop)"
      } catch {
        Write-ArLog "WARN drop default route: $($_.Exception.Message)"
      }
    }
  } catch {
    Write-ArLog "WARN enumerate default routes: $($_.Exception.Message)"
  }
  return @($saved)
}

function Restore-DefaultRoutes([object]$Saved) {
  if (-not $Saved) { return }
  foreach ($item in @($Saved)) {
    try {
      $ifIndex = [int]$item.ifIndex
      $nextHop = [string]$item.nextHop
      $metric = 0
      try { $metric = [int]$item.metric } catch { $metric = 0 }
      if (-not $nextHop) { continue }
      $params = @{
        InterfaceIndex     = $ifIndex
        DestinationPrefix  = "0.0.0.0/0"
        NextHop            = $nextHop
        ErrorAction        = "Stop"
      }
      if ($metric -gt 0) { $params["RouteMetric"] = $metric }
      New-NetRoute @params | Out-Null
      Write-ArLog "restored default route if=$ifIndex gw=$nextHop"
    } catch {
      Write-ArLog "WARN restore default route: $($_.Exception.Message)"
    }
  }
}

function Repair-MsspEchoRequestRules {
  # Never enumerate all firewall rules here (hangs / exceeds Wazuh API timeout).
  # File and Printer Sharing group repair covers Echo Request allows.
  foreach ($name in @("MSSP_QUAR_BLOCK_ICMP_IN", "MSSP_QUAR_BLOCK_ICMP_OUT", "MSSP_ISOLATE_BLOCK_ICMP_OUT", "MSSP_HOLD_BLOCK_ICMP_IN", "MSSP_HOLD_BLOCK_ICMP_OUT")) {
    [void](Invoke-Netsh @("advfirewall", "firewall", "delete", "rule", "name=$name"))
  }
}

function Start-MsspDeferredUnisolateRepair([object]$Deferred) {
  if (-not $Deferred) { return }
  $dir = Join-Path $env:ProgramData "mssp-edr-ar"
  New-Item -ItemType Directory -Path $dir -Force | Out-Null
  $payload = Join-Path $dir "unisolate-deferred.json"
  try {
    ($Deferred | ConvertTo-Json -Compress -Depth 8) | Set-Content -LiteralPath $payload -Encoding ASCII
  } catch {
    Write-ArLog "WARN deferred repair payload: $($_.Exception.Message)"
    return
  }
  $ps64 = Join-Path $env:SystemRoot "sysnative\WindowsPowerShell\v1.0\powershell.exe"
  if (-not (Test-Path -LiteralPath $ps64)) {
    $ps64 = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
  }
  $script = $PSCommandPath
  if (-not $script) { $script = Join-Path $PSScriptRoot "mssp-isolate-host.ps1" }
  try {
    Start-Process -FilePath $ps64 -ArgumentList @(
      "-NoProfile", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass",
      "-File", $script, "deferred-repair", $payload
    ) -WindowStyle Hidden | Out-Null
    Write-ArLog "deferred unisolate repair scheduled payload=$payload"
  } catch {
    Write-ArLog "WARN deferred repair start: $($_.Exception.Message)"
  }
}

function Invoke-MsspDeferredUnisolateRepair([string]$PayloadPath) {
  if (-not (Test-Path -LiteralPath $PayloadPath)) { return }
  try {
    $deferred = Get-Content -LiteralPath $PayloadPath -Raw | ConvertFrom-Json
  } catch {
    Write-ArLog "deferred repair parse failed: $($_.Exception.Message)"
    return
  }
  Write-ArLog "deferred repair begin"
  $execId = ""
  try { $execId = [string]$deferred.execution_id } catch { $execId = "" }
  if ($execId) {
    Send-MsspEdrCallback -ExecutionId $execId -Status "success" -Message "QUARANTINE RELEASED applied=true" -Applied $true -Released $true
  }
  try { Restore-MsspRemoteAccessState -Saved $deferred.remote_access } catch {}
  Repair-MsspRdpAccessExplicit -SavedRemoteAccess $deferred.remote_access
  foreach ($pair in @(
    @{ Prof = "domainprofile"; In = $deferred.domain_in; Out = $deferred.domain_out },
    @{ Prof = "privateprofile"; In = $deferred.private_in; Out = $deferred.private_out },
    @{ Prof = "publicprofile"; In = $deferred.public_in; Out = $deferred.public_out }
  )) {
    $inA = [string]$pair.In; if (-not $inA) { $inA = "Block" }
    $outA = [string]$pair.Out; if (-not $outA -or $outA -eq "Block") { $outA = "Allow" }
    $inPart = if ($inA -eq "Block") { "blockinbound" } else { "allowinbound" }
    $outPart = if ($outA -eq "Block") { "blockoutbound" } else { "allowoutbound" }
    [void](Invoke-Netsh @("advfirewall", "set", $pair.Prof, "firewallpolicy", "$inPart,$outPart"))
  }
  try { Restore-MsspOutboundAllows -SavedNames $deferred.disabled_outbound_allows -MaxSeconds 120 } catch {}
  Repair-MsspInternetConnectivity -SavedRoutes $deferred.default_routes
  try { Restore-MsspLateralAllowRules -SavedRules $deferred.disabled_allow_rules } catch {}
  Repair-MsspEchoRequestRules
  Repair-MsspRdpAccessExplicit -SavedRemoteAccess $null
  Remove-Item -LiteralPath $PayloadPath -Force -ErrorAction SilentlyContinue
  Write-ArLog "deferred repair complete"
}


function Set-FirewallOutboundAllowFast {
  foreach ($profile in @("domainprofile", "privateprofile", "publicprofile")) {
    $r = Invoke-Netsh @("advfirewall", "set", $profile, "firewallpolicy", "blockinbound,allowoutbound")
    Write-ArLog "fast outbound allow $profile rc=$($r.ExitCode)"
  }
}

function Clear-MsspQuarantineRulesFast {
  foreach ($name in @(
    "MSSP_HOLD_BLOCK_RDP_IN", "MSSP_HOLD_BLOCK_RDP_OUT",
    "MSSP_HOLD_BLOCK_SMB_IN", "MSSP_HOLD_BLOCK_WINRM_IN",
    "MSSP_HOLD_BLOCK_ICMP_IN", "MSSP_HOLD_BLOCK_ICMP_OUT",
    "MSSP_QUAR_BLOCK_RDP_IN", "MSSP_QUAR_BLOCK_RDP_OUT",
    "MSSP_QUAR_BLOCK_SMB_IN", "MSSP_QUAR_BLOCK_SMB_OUT",
    "MSSP_QUAR_BLOCK_WINRM_IN", "MSSP_QUAR_BLOCK_ICMP_IN", "MSSP_QUAR_BLOCK_ICMP_OUT",
    "MSSP_QUAR_BLOCK_RPC_IN", "MSSP_QUAR_BLOCK_SSH_IN", "MSSP_QUAR_BLOCK_SSH_OUT"
  )) {
    [void](Invoke-Netsh @("advfirewall", "firewall", "delete", "rule", "name=$name"))
  }
}

function Remove-IsolationRulesFast([string]$ExecutionId = "") {
  [void](Invoke-MsspUnisolate -ExecutionId $ExecutionId)
  return $ExecutionId
}

function Remove-IsolationRules {
  [void](Invoke-MsspUnisolate -ExecutionId "")
  return ""
}

function Add-IsolationRules([int]$Seconds, [string]$ExecutionId = "") {
  Write-ArLog "QUARANTINE begin manager=$Manager seconds=$Seconds exec=$ExecutionId (Wazuh ports only; hold until unisolate)"
  Remove-Item -LiteralPath $CancelFile -Force -ErrorAction SilentlyContinue
  Stop-StaleAutoRelease

  $state = Get-FirewallStateObject
  $state["seconds"] = 0
  $state["execution_id"] = $ExecutionId
  $state["remote_access"] = Get-MsspRemoteAccessState
  $state["default_routes"] = @(Get-MsspDefaultRoutesSnapshot)
  $state["disabled_outbound_allows"] = @()
  $state["disabled_allow_rules"] = @()
  Save-MsspIsolateState $state

  # Contain FIRST. Clearing leftover MSSP rules is fine; never enumerate every
  # Windows firewall rule (that hung 32-bit execd and skipped default-deny).
  Clear-MsspQuarantineRulesFast
  [void](Invoke-Netsh @("advfirewall", "firewall", "delete", "rule", "name=MSSP_RDP_RESTORE_IN"))

  Resolve-MsspCallbackAllowIps

  $allowSpecs = @(
    @{ Name = "MSSP_QUAR_ALLOW_WAZUH_OUT_1514"; Dir = "out"; Extra = @("protocol=tcp", "remoteip=$Manager", "remoteport=1514") },
    @{ Name = "MSSP_QUAR_ALLOW_WAZUH_OUT_1515"; Dir = "out"; Extra = @("protocol=tcp", "remoteip=$Manager", "remoteport=1515") },
    @{ Name = "MSSP_QUAR_ALLOW_WAZUH_IN_1514"; Dir = "in"; Extra = @("protocol=tcp", "remoteip=$Manager", "localport=1514") },
    @{ Name = "MSSP_QUAR_ALLOW_WAZUH_IN_1515"; Dir = "in"; Extra = @("protocol=tcp", "remoteip=$Manager", "localport=1515") },
    @{ Name = "MSSP_QUAR_ALLOW_WAZUH_OUT_UDP1514"; Dir = "out"; Extra = @("protocol=udp", "remoteip=$Manager", "remoteport=1514") },
    @{ Name = "MSSP_QUAR_ALLOW_CTRLPLANE_OUT"; Dir = "out"; Extra = @("protocol=tcp", "remoteip=$ControlPlane", "remoteport=8000,443,80") },
    @{ Name = "MSSP_QUAR_ALLOW_CTRLPLANE_IN"; Dir = "in"; Extra = @("protocol=tcp", "remoteip=$ControlPlane") },
    @{ Name = "MSSP_QUAR_ALLOW_DNS_UDP"; Dir = "out"; Extra = @("protocol=udp", "remoteport=53") },
    @{ Name = "MSSP_QUAR_ALLOW_DNS_TCP"; Dir = "out"; Extra = @("protocol=tcp", "remoteport=53") },
    @{ Name = "MSSP_QUAR_ALLOW_DHCP"; Dir = "out"; Extra = @("protocol=udp", "remoteport=67,68") },
    @{ Name = "MSSP_QUAR_ALLOW_LOOPBACK_OUT"; Dir = "out"; Extra = @("remoteip=127.0.0.1") },
    @{ Name = "MSSP_QUAR_ALLOW_LOOPBACK_IN"; Dir = "in"; Extra = @("remoteip=127.0.0.1") }
  )
  # Public callback hostname IPs (Cloudflare / api.kevantic.com) — required for WAN verify.
  $cbIdx = 0
  foreach ($ip in @($CallbackAllowIps)) {
    if (-not $ip) { continue }
    if ($ip -eq $ControlPlane) { continue }
    $cbIdx++
    $allowSpecs += @{
      Name = "MSSP_QUAR_ALLOW_CALLBACK_OUT_$cbIdx"
      Dir = "out"
      Extra = @("protocol=tcp", "remoteip=$ip", "remoteport=443,80")
    }
  }
  Write-ArLog "allow-list wazuh_manager=$Manager control_plane=$ControlPlane callback_ips=$($CallbackAllowIps -join ',')"
  foreach ($spec in $allowSpecs) {
    $args = @(
      "advfirewall", "firewall", "add", "rule",
      "name=$($spec.Name)", "dir=$($spec.Dir)", "action=allow",
      "enable=yes", "profile=any"
    ) + $spec.Extra
    $r = Invoke-Netsh $args
    if ($r.ExitCode -ne 0) {
      Write-ArLog "WARN allow $($spec.Name) rc=$($r.ExitCode) $($r.StdErr.Trim())"
    }
  }

  Add-LateralBlockRules
  if (Test-MsspUnisolateRequested) {
    Write-ArLog "QUARANTINE aborted mid-isolate (unisolate won the race)"
    [void](Remove-IsolationRulesFast -ExecutionId $ExecutionId)
    return $false
  }
  $ok = Set-FirewallDefaultActions -Inbound "Block" -Outbound "Block"
  $state["disabled_allow_rules"] = @(Disable-MsspLateralAllowRules)
  Save-MsspIsolateState $state
  if (Test-MsspUnisolateRequested) {
    Write-ArLog "QUARANTINE aborted before session drop / watchdog"
    [void](Remove-IsolationRulesFast -ExecutionId $ExecutionId)
    return $false
  }
  # Prove + report before watchdog / effect probes (those can hang under execd).
  if ($ok) {
    "active manager=$Manager since=$(Get-Date -Format o)" | Set-Content -LiteralPath $MarkerFile -Encoding ASCII
    try {
      icacls $MarkerFile /inheritance:r /grant:r "SYSTEM:F" /grant:r "BUILTIN\Administrators:F" | Out-Null
    } catch {}
    Write-ArLog "QUARANTINE ACTIVE applied=true (Wazuh 1514/1515 only; hold until Un-isolate)"
    if ($ExecutionId) {
      Send-MsspEdrCallback -ExecutionId $ExecutionId -Status "success" -Message "QUARANTINE ACTIVE applied=true" -Applied $true -Released $false
    }
  } else {
    Write-ArLog "QUARANTINE FAILED applied=false -- host NOT contained; do not trust UI dispatch alone"
    if ($ExecutionId) {
      Send-MsspEdrCallback -ExecutionId $ExecutionId -Status "failed" -Message "QUARANTINE FAILED applied=false" -Applied $false -Released $false
    }
    return $false
  }
  Stop-InteractiveRemoteSessions
  if (Test-MsspUnisolateRequested) {
    Write-ArLog "QUARANTINE aborted before watchdog"
    [void](Remove-IsolationRulesFast -ExecutionId $ExecutionId)
    return $false
  }
  Install-MsspQuarantineWatchdog

  $effective = Test-QuarantineEffect
  if (-not $effective) {
    Write-ArLog "WARN Test-QuarantineEffect soft-fail after applied=true callback"
  }

  Write-ArLog "hold-until-unisolate exec=$ExecutionId (timed auto-release disabled)"
  return $true
}

function Convert-ArArgToRaw([object]$Value) {
  if ($null -eq $Value) { return "" }
  # cmd.exe argv-quoting can turn JSON into ScriptBlock/Hashtable; normalize.
  if ($Value -is [System.Management.Automation.ScriptBlock]) {
    return [string]$Value
  }
  if ($Value -is [hashtable] -or $Value -is [System.Collections.IDictionary] -or $Value -is [pscustomobject]) {
    try { return ($Value | ConvertTo-Json -Compress -Depth 20) } catch { return [string]$Value }
  }
  return [string]$Value
}

$raw = ""
$executionId = ""
if ($args.Count -ge 1 -and [string]$args[0] -eq "complete-outbound") {
  $payloadPath = if ($args.Count -gt 1) { [string]$args[1] } else { "" }
  if ($payloadPath -and (Test-Path -LiteralPath $payloadPath)) {
    try {
      $names = @((Get-Content -LiteralPath $payloadPath -Raw | ConvertFrom-Json))
      [void](Restore-MsspOutboundAllows -SavedNames $names -MaxSeconds 120)
    } catch {
      Write-ArLog "complete-outbound parse failed: $($_.Exception.Message)"
    }
    Remove-Item -LiteralPath $payloadPath -Force -ErrorAction SilentlyContinue
  }
  exit 0
}

if ($args.Count -ge 1 -and [string]$args[0] -eq "deferred-repair") {
  # Legacy path: run full unisolate if a stale deferred payload exists.
  $payloadPath = if ($args.Count -gt 1) { [string]$args[1] } else { "" }
  $execId = ""
  if ($payloadPath -and (Test-Path -LiteralPath $payloadPath)) {
    try {
      $legacy = Get-Content -LiteralPath $payloadPath -Raw | ConvertFrom-Json
      try { $execId = [string]$legacy.execution_id } catch { $execId = "" }
    } catch {}
    Remove-Item -LiteralPath $payloadPath -Force -ErrorAction SilentlyContinue
  }
  [void](Invoke-MsspUnisolate -ExecutionId $execId)
  exit 0
}
if (-not $env:MSSP_ISOLATE_REEXEC -and -not $env:MSSP_SKIP_SCRIPT_SYNC) {
  $sharedPs1 = @(
    (Join-Path $PSScriptRoot "..\..\shared\mssp-isolate-host.ps1"),
    "${env:ProgramFiles(x86)}\ossec-agent\shared\mssp-isolate-host.ps1",
    "$env:ProgramFiles\ossec-agent\shared\mssp-isolate-host.ps1"
  ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
  if ($sharedPs1 -and $PSCommandPath -and (Test-Path -LiteralPath $PSCommandPath)) {
    try {
      $srcHash = (Get-FileHash -LiteralPath $sharedPs1 -Algorithm SHA256).Hash
      $selfHash = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash
      if ($srcHash -ne $selfHash) {
        Copy-Item -LiteralPath $sharedPs1 -Destination $PSCommandPath -Force
        $env:MSSP_ISOLATE_REEXEC = "1"
        Write-ArLog "replaced stale isolate script from Manager shared; re-exec"
        & $PSCommandPath @args
        exit $LASTEXITCODE
      }
    } catch {
      Write-ArLog "WARN shared self-sync: $($_.Exception.Message)"
    }
  }
}
Write-ArLog "STARTED args=$($args.Count)"
if ($args.Count -gt 0) {
  $a0 = Convert-ArArgToRaw $args[0]
  if (@("delete", "remove", "unisolate") -contains $a0.ToLowerInvariant()) {
    $executionId = if ($args.Count -gt 1) { [string](Convert-ArArgToRaw $args[1]) } else { "" }
    [void](Invoke-MsspUnisolate -ExecutionId $executionId -ForceFullRestore)
    exit 0
  }
  if ($a0 -match '[\{\[]') {
    $raw = $a0
  }
}
if (-not $raw) {
  try { $raw = [Console]::In.ReadLine() } catch { $raw = "" }
}
Write-ArLog "INPUT_LEN=$($raw.Length)"
$j = $null
try { if ($raw) { $j = $raw | ConvertFrom-Json } } catch {}

$cmd = "add"
$extra = @()
if ($j) {
  if ($j.command) { $cmd = [string]$j.command }
  if ($j.parameters -and $j.parameters.extra_args) { $extra = @($j.parameters.extra_args) }
  elseif ($j.arguments) { $extra = @($j.arguments) }
}
if ($extra.Count -gt 0 -and @("delete", "remove", "unisolate") -contains ([string]$extra[0]).ToLowerInvariant()) {
  $cmd = "delete"
  if ($extra.Count -gt 1) { $executionId = [string]$extra[1] }
}
$seconds = 0
if ($extra.Count -gt 0 -and $cmd -ne "delete") {
  $first = [string]$extra[0]
  if ($first.ToLowerInvariant() -notin @("hold", "delete", "remove", "unisolate")) {
    try { $seconds = [int]$first } catch { $seconds = 0 }
  }
  if ($extra.Count -gt 1) { $executionId = [string]$extra[1] }
  # AR args: [hold|delete, execution_id, callback_url] — prefer Manager-provided URL (WAN).
  if ($extra.Count -gt 2) {
    $argCb = [string]$extra[2]
    if ($argCb -match '^https?://') { $CallbackUrl = $argCb.Trim() }
  }
}
if ($cmd -eq "delete" -and $extra.Count -gt 2) {
  $argCb = [string]$extra[2]
  if ($argCb -match '^https?://') { $CallbackUrl = $argCb.Trim() }
}
if ($seconds -lt 0) { $seconds = 0 }
if ($seconds -gt 86400) { $seconds = 86400 }
$allowTimed = $false
if (Test-Path -LiteralPath $envFile) {
  Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match '^\s*MSSP_ALLOW_TIMED_ISOLATE\s*=\s*1\s*$') { $allowTimed = $true }
  }
}
if (-not $allowTimed) {
  $seconds = 0
}
Write-ArLog "execution_id=$executionId cmd=$cmd seconds=$seconds timed=$allowTimed"

$explicitUnisolate = $false
if ($extra.Count -gt 0 -and @("delete", "remove", "unisolate") -contains ([string]$extra[0]).ToLowerInvariant()) {
  $explicitUnisolate = $true
}

if ($explicitUnisolate) {
  $fromState = Invoke-MsspUnisolate -ExecutionId $executionId
  if (-not $executionId -and $fromState) { $executionId = $fromState }
} elseif (@("delete", "remove") -contains $cmd.ToLowerInvariant()) {
  Write-ArLog "ignored wazuh timed delete cmd=$cmd -- hold until Un-isolate"
  exit 0
} else {
  $applied = [bool](Add-IsolationRules -Seconds $seconds -ExecutionId $executionId)
  # Callback already sent inside Add-IsolationRules (before watchdog hang risk).
  if (-not $applied) {
    Write-ArLog "isolate applied=false (callback already attempted)"
  }
}
exit 0
