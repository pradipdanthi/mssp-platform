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
# Prefer callback URL host when set (KB-091: quarantine must still reach control plane).
if ($CallbackUrl) {
  try {
    $cbHost = ([Uri]$CallbackUrl).Host
    if ($cbHost -and $cbHost -match '^\d{1,3}(\.\d{1,3}){3}$') {
      $ControlPlane = $cbHost
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
    "MSSP_QUAR_ALLOW_DHCP",
    "MSSP_QUAR_ALLOW_LOOPBACK_OUT",
    "MSSP_QUAR_ALLOW_LOOPBACK_IN",
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
    "MSSP_HOLD_BLOCK_ICMP_OUT"
  )) {
    [void](Invoke-Netsh @("advfirewall", "firewall", "delete", "rule", "name=$name"))
  }
}

function Disable-MsspLateralAllowRules {
  # Default-deny alone is NOT enough: Windows keeps explicit ALLOW rules for
  # Remote Desktop / SMB / WinRM / File Sharing. Those still permit traffic (and
  # established RDP sessions keep flowing). Disable those allows during quarantine
  # and remember EXACT prior Enabled state for restore.
  $saved = @()
  $patterns = @(
    "*Remote Desktop*",
    "*Remote Assistance*",
    "*File and Printer Sharing*",
    "*Windows Remote Management*",
    "*WinRM*",
    "*Remote Event Log*",
    "*Remote Service Management*",
    "*Remote Scheduled Tasks*",
    "*Echo Request*"
  )
  try {
    $rules = Get-NetFirewallRule -ErrorAction SilentlyContinue |
      Where-Object {
        $dn = [string]$_.DisplayName
        $dg = [string]$_.DisplayGroup
        foreach ($p in $patterns) {
          if ($dn -like $p -or $dg -like $p) { return $true }
        }
        return $false
      }
    foreach ($rule in $rules) {
      $wasEnabled = [bool]($rule.Enabled -eq "True" -or $rule.Enabled -eq $true)
      $saved += [ordered]@{
        name        = [string]$rule.Name
        display     = [string]$rule.DisplayName
        was_enabled = $wasEnabled
      }
      if ($wasEnabled) {
        try {
          Disable-NetFirewallRule -Name $rule.Name -ErrorAction Stop
          Write-ArLog "Disabled allow rule name=$($rule.Name) display=$($rule.DisplayName)"
        } catch {
          Write-ArLog "WARN disable rule $($rule.Name): $($_.Exception.Message)"
        }
      }
    }
  } catch {
    Write-ArLog "WARN enumerating lateral allow rules: $($_.Exception.Message)"
  }
  return @($saved)
}

function Restore-MsspLateralAllowRules([object]$SavedRules) {
  if (-not $SavedRules) { return }
  foreach ($item in @($SavedRules)) {
    $name = $null
    $wasEnabled = $true
    if ($item -is [string]) {
      # legacy state format: bare rule name list
      $name = $item
      $wasEnabled = $true
    } else {
      try { $name = [string]$item.name } catch { $name = $null }
      try {
        if ($null -ne $item.was_enabled) { $wasEnabled = [bool]$item.was_enabled }
      } catch {}
    }
    if (-not $name) { continue }
    try {
      if ($wasEnabled) {
        Enable-NetFirewallRule -Name $name -ErrorAction Stop
        Write-ArLog "Restored ENABLED allow rule name=$name"
      } else {
        Disable-NetFirewallRule -Name $name -ErrorAction SilentlyContinue
        Write-ArLog "Restored DISABLED allow rule name=$name"
      }
    } catch {
      Write-ArLog ("WARN restore rule ${name}: " + $_.Exception.Message)
    }
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
  # True containment drops interactive remote sessions (SOC should use agent path).
  Write-ArLog "Dropping interactive remote sessions (RDP/console shadow) for containment"
  try {
    $sessions = & qwinsta 2>$null
    foreach ($line in $sessions) {
      if ($line -match 'rdp-tcp#\s*(\d+)' -or $line -match '^\s*(\S+)\s+\S+\s+(\d+)\s+Active') {
        $id = $null
        if ($line -match 'rdp-tcp#\d+\s+(\S+)\s+(\d+)') { $id = $Matches[2] }
        elseif ($line -match '^\s*\S+\s+\S+\s+(\d+)\s+Active') { $id = $Matches[1] }
        if ($id -and $id -ne "0") {
          try {
            & rwinsta $id 2>$null
            Write-ArLog "reset session id=$id"
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

  $rules = Invoke-Netsh @("advfirewall", "firewall", "show", "rule", "name=MSSP_QUAR_ALLOW_MANAGER_OUT")
  if ($rules.StdOut -match "MSSP_QUAR_ALLOW_MANAGER_OUT" -and $rules.StdOut -notmatch "No rules match") {
    $result.manager_allow_rule = $true
  }

  # Best-effort gateway probe (ICMP). Failure/timeout = expected under quarantine.
  # Success = quarantine NOT effective for at least ICMP (policy not applied / overridden).
  try {
    $gw = $null
    $cfg = Get-NetIPConfiguration -ErrorAction SilentlyContinue |
      Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq "Up" } |
      Select-Object -First 1
    if ($cfg) { $gw = [string]$cfg.IPv4DefaultGateway.NextHop }
    if ($gw) {
      $ping = Test-Connection -ComputerName $gw -Count 1 -Quiet -ErrorAction SilentlyContinue
      $result.gateway_probe_blocked = (-not $ping)
      $result.notes += "gateway=$gw icmp_blocked=$($result.gateway_probe_blocked)"
    } else {
      $result.notes += "gateway_unknown"
    }
  } catch {
    $result.notes += "gateway_probe_error"
    $result.gateway_probe_blocked = $true
  }

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

function Repair-MsspEchoRequestRules {
  # Ping (ICMPv4 echo) is not restored by "inbound Block / outbound Allow" defaults.
  # Isolate disables File and Printer Sharing Echo Request allows; Un-isolate must
  # turn them back on even if the snapshot was already consumed (double-lift).
  try {
    $rules = Get-NetFirewallRule -ErrorAction SilentlyContinue |
      Where-Object { [string]$_.DisplayName -like "*Echo Request*" }
    foreach ($rule in $rules) {
      try {
        Enable-NetFirewallRule -Name $rule.Name -ErrorAction Stop
        Write-ArLog "Repair enabled echo rule name=$($rule.Name) display=$($rule.DisplayName)"
      } catch {
        Write-ArLog "WARN enable echo $($rule.Name): $($_.Exception.Message)"
      }
    }
  } catch {
    Write-ArLog "WARN echo repair: $($_.Exception.Message)"
  }
  foreach ($name in @("MSSP_QUAR_BLOCK_ICMP_IN", "MSSP_QUAR_BLOCK_ICMP_OUT", "MSSP_ISOLATE_BLOCK_ICMP_OUT")) {
    [void](Invoke-Netsh @("advfirewall", "firewall", "delete", "rule", "name=$name"))
  }
}


function Remove-IsolationRules {
  # IMPORTANT order:
  # 1) Restore profile defaults FIRST (outbound Allow) while Manager/control-plane
  #    allow rules still exist — otherwise default-deny + clearing allows traps the host
  #    and the release callback cannot reach the control plane.
  # 2) Restore prior Enabled state for lateral/ICMP rules we touched.
  # 3) Remove temporary MSSP_* quarantine rules.
  # 4) Re-enable Echo Request (ping) even if snapshot was already consumed.
  # 5) Clear marker.
  $CancelFile = Join-Path $env:ProgramData "mssp-edr-isolate-cancel.flag"
  try { "cancelled" | Set-Content -LiteralPath $CancelFile -Encoding ASCII } catch {}

  $hadSnapshot = Test-Path -LiteralPath $StateFile
  $hadMarker = Test-Path -LiteralPath $MarkerFile
  $savedRules = @()
  $executionIdFromState = ""
  $restoredProfiles = $false
  if ($hadSnapshot) {
    try {
      $state = Get-Content -LiteralPath $StateFile -Raw | ConvertFrom-Json
      try { $executionIdFromState = [string]$state.execution_id } catch { $executionIdFromState = "" }
      foreach ($name in @("Domain", "Private", "Public")) {
        $key = $name.ToLowerInvariant()
        $inA = $state."${key}_in"; if (-not $inA) { $inA = "Block" }
        $outA = $state."${key}_out"; if (-not $outA) { $outA = "Allow" }
        $en = Convert-ToMsspBool $state."${key}_enabled" $true
        try {
          Set-NetFirewallProfile -Profile $name `
            -DefaultInboundAction $inA `
            -DefaultOutboundAction $outA `
            -Enabled $en `
            -ErrorAction Stop | Out-Null
          Write-ArLog "restore profile $name in=$inA out=$outA enabled=$en"
          $restoredProfiles = $true
        } catch {
          Write-ArLog "restore $name Set-NetFirewallProfile failed: $($_.Exception.Message)"
          $inPart = if ($inA -eq "Block") { "blockinbound" } else { "allowinbound" }
          $outPart = if ($outA -eq "Block") { "blockoutbound" } else { "allowoutbound" }
          $prof = switch ($name) {
            "Domain" { "domainprofile" }
            "Private" { "privateprofile" }
            default { "publicprofile" }
          }
          $r = Invoke-Netsh @("advfirewall", "set", $prof, "firewallpolicy", "$inPart,$outPart")
          Write-ArLog "restore $name netsh rc=$($r.ExitCode)"
          if ($r.ExitCode -eq 0) { $restoredProfiles = $true }
        }
      }
      if ($state.disabled_allow_rules) {
        $savedRules = @($state.disabled_allow_rules)
      }
      Remove-Item -LiteralPath $StateFile -Force -ErrorAction SilentlyContinue
      Write-ArLog "QUARANTINE lift - snapshot applied (profiles first)"
    } catch {
      Write-ArLog "QUARANTINE lift - state parse failed: $($_.Exception.Message)"
    }
  }
  if (-not $restoredProfiles) {
    if ($hadSnapshot -or $hadMarker) {
      [void](Set-FirewallDefaultActions -Inbound "Block" -Outbound "Allow")
      Write-ArLog "QUARANTINE lift - fallback inbound=Block outbound=Allow"
    } else {
      Write-ArLog "QUARANTINE lift - already released; skip profile fallback"
    }
  }

  # Verify outbound actually restored; retry fallback if still blocked.
  try {
    $stillBlocked = @(Get-NetFirewallProfile -Profile Domain, Private, Public -ErrorAction Stop |
      Where-Object { $_.DefaultOutboundAction -eq "Block" }).Count
    if ($stillBlocked -gt 0 -and ($hadSnapshot -or $hadMarker)) {
      Write-ArLog "WARN outbound still Block on $stillBlocked/3 profiles — forcing Allow"
      [void](Set-FirewallDefaultActions -Inbound "Block" -Outbound "Allow")
    }
  } catch {
    Write-ArLog "WARN post-restore profile check failed: $($_.Exception.Message)"
    if ($hadSnapshot -or $hadMarker) {
      [void](Set-FirewallDefaultActions -Inbound "Block" -Outbound "Allow")
    }
  }

  Restore-MsspLateralAllowRules -SavedRules $savedRules
  Clear-MsspAllowRules
  Repair-MsspEchoRequestRules
  Remove-Item -LiteralPath $MarkerFile -Force -ErrorAction SilentlyContinue
  return $executionIdFromState
}

function Add-IsolationRules([int]$Seconds, [string]$ExecutionId = "") {
  Write-ArLog "QUARANTINE begin manager=$Manager control_plane=$ControlPlane seconds=$Seconds exec=$ExecutionId"
  Clear-MsspAllowRules

  # Snapshot BEFORE mutating anything so lift returns to exact prior state.
  $state = Get-FirewallStateObject
  $state["seconds"] = $Seconds
  $state["execution_id"] = $ExecutionId
  $state["disabled_allow_rules"] = @(Disable-MsspLateralAllowRules)

  try {
    $dir = Split-Path $StateFile -Parent
    if (-not (Test-Path -LiteralPath $dir)) {
      New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    ($state | ConvertTo-Json -Compress -Depth 6) | Set-Content -LiteralPath $StateFile -Encoding ASCII
    Write-ArLog ("STATE saved rules=" + @($state.disabled_allow_rules).Count)
  } catch {
    Write-ArLog "WARN state file: $($_.Exception.Message)"
  }

  # SOC continuity allow-list BEFORE default-deny
  # Control plane must stay reachable for applied=true callback (else UI never Verified).
  $allowSpecs = @(
    @{ Name = "MSSP_QUAR_ALLOW_MANAGER_OUT"; Dir = "out"; Extra = @("remoteip=$Manager") },
    @{ Name = "MSSP_QUAR_ALLOW_MANAGER_IN"; Dir = "in"; Extra = @("remoteip=$Manager") },
    @{ Name = "MSSP_QUAR_ALLOW_CTRLPLANE_OUT"; Dir = "out"; Extra = @("remoteip=$ControlPlane") },
    @{ Name = "MSSP_QUAR_ALLOW_CTRLPLANE_IN"; Dir = "in"; Extra = @("remoteip=$ControlPlane") },
    @{ Name = "MSSP_QUAR_ALLOW_DHCP"; Dir = "out"; Extra = @("protocol=udp", "remoteport=67,68") },
    @{ Name = "MSSP_QUAR_ALLOW_LOOPBACK_OUT"; Dir = "out"; Extra = @("remoteip=127.0.0.1") },
    @{ Name = "MSSP_QUAR_ALLOW_LOOPBACK_IN"; Dir = "in"; Extra = @("remoteip=127.0.0.1") }
  )
  Write-ArLog "allow-list manager=$Manager control_plane=$ControlPlane"
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
  $ok = Set-FirewallDefaultActions -Inbound "Block" -Outbound "Block"
  # Drop live RDP/etc. -- default-deny alone often leaves established sessions up.
  Stop-InteractiveRemoteSessions

  $effective = $false
  if ($ok) {
    $effective = Test-QuarantineEffect
  } else {
    Write-ArLog "ERROR default-deny not applied -- possible Group Policy lock on Windows Firewall"
  }

  if ($effective) {
    "active manager=$Manager since=$(Get-Date -Format o)" | Set-Content -LiteralPath $MarkerFile -Encoding ASCII
    Write-ArLog "QUARANTINE ACTIVE applied=true (default-deny + RDP/SMB/WinRM/ICMP blocked; sessions reset)"
  } else {
    Write-ArLog "QUARANTINE FAILED applied=false -- host NOT contained; do not trust UI dispatch alone"
  }

  # 0 = hold until SOC Un-isolate. Positive = timed auto-release (lab/test only).
  if ($Seconds -gt 0) {
    $exeEsc = $ExecutionId -replace "'", "''"
    $cancelPath = Join-Path $env:ProgramData "mssp-edr-isolate-cancel.flag"
    Remove-Item -LiteralPath $cancelPath -Force -ErrorAction SilentlyContinue
    $releaseCmd = @"
Start-Sleep -Seconds $Seconds
if (Test-Path -LiteralPath '$cancelPath') { exit 0 }
& '$PSCommandPath' delete '$exeEsc'
"@
    Start-Process -FilePath "powershell.exe" -ArgumentList @(
      "-NoProfile", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-Command", $releaseCmd
    ) -WindowStyle Hidden | Out-Null
    Write-ArLog "auto-release armed seconds=$Seconds exec=$ExecutionId"
  } else {
    Write-ArLog "hold-until-unisolate exec=$ExecutionId"
  }

  return [bool]$effective
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
if (-not $env:MSSP_ISOLATE_REEXEC) {
  $sharedPs1 = @(
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
    $fromState = Remove-IsolationRules
    if (-not $executionId -and $fromState) { $executionId = $fromState }
    Send-MsspEdrCallback -ExecutionId $executionId -Status "success" -Message "QUARANTINE RELEASED applied=true" -Applied $true -Released $true
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
  try { $seconds = [int]$extra[0] } catch { $seconds = 0 }
  if ($extra.Count -gt 1) { $executionId = [string]$extra[1] }
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

if (@("delete", "remove") -contains $cmd.ToLowerInvariant()) {
  $fromState = Remove-IsolationRules
  if (-not $executionId -and $fromState) { $executionId = $fromState }
  Send-MsspEdrCallback -ExecutionId $executionId -Status "success" -Message "QUARANTINE RELEASED applied=true" -Applied $true -Released $true
} else {
  $applied = [bool](Add-IsolationRules -Seconds $seconds -ExecutionId $executionId)
  if ($applied) {
    Send-MsspEdrCallback -ExecutionId $executionId -Status "success" -Message "QUARANTINE ACTIVE applied=true" -Applied $true -Released $false
  } else {
    Send-MsspEdrCallback -ExecutionId $executionId -Status "failed" -Message "QUARANTINE FAILED applied=false" -Applied $false -Released $false
  }
}
exit 0
