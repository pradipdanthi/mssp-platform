#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Install MSSP Windows EDR Active Response scripts (kill / isolate / block-hash).

.DESCRIPTION
  Day-one and remediation installer. Copies AR scripts into the endpoint agent
  active-response\bin folder, writes mssp-ar.env, and enables automatic shared/
  sync (scheduled task). Safe to re-run (idempotent).

  Manager IP defaults from agent ossec.conf when present (appliance or WAN edge).
  Callback defaults to the public API so LAN and WAN agents both verify.

.PARAMETER ManagerIp
  Wazuh Manager IP allowed during isolation. Empty = read from ossec.conf.

.PARAMETER CallbackUrl
  Control-plane EDR callback URL (KB-091). Default: https://api.kevantic.com/...

.PARAMETER CallbackKey
  Shared callback key (SOC sync key until per-execution tokens land).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\Install-MsspWindowsEdrAr.ps1
#>
[CmdletBinding()]
param(
  [string]$ManagerIp = "",
  [string]$ControlPlaneIp = "192.168.0.201",
  [string]$CallbackUrl = "https://api.kevantic.com/v1/edr/actions/callback",
  [string]$CallbackKey = ""
)

$ErrorActionPreference = "Stop"

# Fingerprint -- refuse to run if this file was overwritten with another AR script.
$selfHead = Get-Content -LiteralPath $PSCommandPath -TotalCount 5 -ErrorAction SilentlyContinue
if (-not ($selfHead -join "`n" | Select-String -SimpleMatch "Install MSSP Windows EDR Active Response")) {
  throw "Wrong installer file content. Re-copy mssp-windows-edr-ar-remediate.zip from the control plane and extract fresh."
}

function Write-Step([string]$Message) {
  Write-Host "[MSSP-EDR-AR] $Message"
}

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($id)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw "Run elevated (Run as Administrator)."
}

$Here = $PSScriptRoot
if (-not $Here) { $Here = Split-Path -Parent $MyInvocation.MyCommand.Path }

$required = @(
  "mssp-kill-process.cmd", "mssp-kill-process.ps1",
  "mssp-isolate-host.cmd", "mssp-isolate-host.ps1",
  "mssp-block-hash.cmd", "mssp-block-hash.ps1",
  "Sync-MsspEdrAr.ps1",
  "Watch-MsspQuarantine.ps1"
)
$optionalCopy = @("Test-MsspQuarantineProof.ps1", "mssp-ar.env.defaults")
foreach ($f in $required) {
  if (-not (Test-Path -LiteralPath (Join-Path $Here $f))) {
    throw "Missing $f next to this installer"
  }
}

$agentRoots = @(
  "${env:ProgramFiles(x86)}\ossec-agent",
  "$env:ProgramFiles\ossec-agent"
)
$agentRoot = $agentRoots | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $agentRoot) {
  throw "Endpoint agent not found. Install the Windows agent first, then re-run this script."
}

# Prefer Manager IP already configured on the agent (appliance vs WAN edge).
if (-not $ManagerIp) {
  $conf = Join-Path $agentRoot "etc\ossec.conf"
  if (Test-Path -LiteralPath $conf) {
    try {
      [xml]$xml = Get-Content -LiteralPath $conf -Raw
      $addr = $xml.ossec_config.client.server.address
      if ($addr -is [Array]) { $addr = $addr | Select-Object -First 1 }
      $ManagerIp = [string]$addr
    } catch {
      $raw = Get-Content -LiteralPath $conf -Raw -ErrorAction SilentlyContinue
      if ($raw -match '<address>\s*([^<]+)\s*</address>') {
        $ManagerIp = $Matches[1].Trim()
      }
    }
  }
}
if (-not $ManagerIp) { $ManagerIp = "192.168.0.211" }

if (-not $CallbackKey) {
  $CallbackKey = [string]$env:MSSP_CALLBACK_KEY
}
if (-not $CallbackKey) {
  foreach ($kf in @(
    (Join-Path $Here "mssp-callback.key"),
    (Join-Path $env:ProgramData "mssp-edr-ar\mssp-callback.key")
  )) {
    if (Test-Path -LiteralPath $kf) {
      $CallbackKey = (Get-Content -LiteralPath $kf -Raw).Trim()
      if ($CallbackKey) { break }
    }
  }
}

$dest = Join-Path $agentRoot "active-response\bin"
if (-not (Test-Path -LiteralPath $dest)) {
  New-Item -ItemType Directory -Path $dest -Force | Out-Null
}

Write-Step "Installing AR scripts into $dest"
foreach ($f in $required) {
  Copy-Item -LiteralPath (Join-Path $Here $f) -Destination (Join-Path $dest $f) -Force
}
$pd = Join-Path $env:ProgramData "mssp-edr-ar"
New-Item -ItemType Directory -Path $pd -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $Here "Watch-MsspQuarantine.ps1") -Destination (Join-Path $pd "Watch-MsspQuarantine.ps1") -Force
Copy-Item -LiteralPath (Join-Path $Here "Sync-MsspEdrAr.ps1") -Destination (Join-Path $pd "Sync-MsspEdrAr.ps1") -Force
foreach ($f in $optionalCopy) {
  $src = Join-Path $Here $f
  if (Test-Path -LiteralPath $src) {
    Copy-Item -LiteralPath $src -Destination (Join-Path $dest $f) -Force
  }
}

$etcDir = Join-Path $agentRoot "etc"
New-Item -ItemType Directory -Path $etcDir -Force | Out-Null
$envOut = Join-Path $dest "mssp-ar.env"
$envEtc = Join-Path $etcDir "mssp-ar.env"
$envLines = @(
  "WAZUH_MANAGER_IP=$ManagerIp",
  "MSSP_CONTROL_PLANE_IP=$ControlPlaneIp",
  "MSSP_CALLBACK_URL=$CallbackUrl"
)
if ($CallbackKey) {
  $envLines += "MSSP_CALLBACK_KEY=$CallbackKey"
  Set-Content -LiteralPath (Join-Path $pd "mssp-callback.key") -Value $CallbackKey -Encoding ASCII
  $keyState = "present"
} else {
  Write-Step "WARNING: CallbackKey empty - isolate will stay Dispatched (no applied=true callback)."
  $keyState = "MISSING"
}
$envLines | Set-Content -LiteralPath $envOut -Encoding ASCII
$envLines | Set-Content -LiteralPath $envEtc -Encoding ASCII
Write-Step "Wrote $envOut (callback URL set; key=$keyState; manager=$ManagerIp)"

Write-Step "Restarting WazuhSvc..."
Restart-Service -Name WazuhSvc -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Get-Service -Name WazuhSvc | Format-List Name, Status

$syncRun = Join-Path $pd "Sync-MsspEdrAr.ps1"
if (Test-Path -LiteralPath $syncRun) {
  & $syncRun
  $tr = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$syncRun`""
  schtasks.exe /Create /TN "MSSP-EDR-AR-Sync" /SC MINUTE /MO 1 /RU SYSTEM /RL HIGHEST /TR $tr /F | Out-Null
  Write-Step "Scheduled MSSP-EDR-AR-Sync (every 1 minute) - auto shared apply + env refresh"
}

$lio = Join-Path $agentRoot "local_internal_options.conf"
$need = @(
  "wazuh_command.remote_commands=1",
  "logcollector.remote_commands=1"
)
$existing = ""
if (Test-Path -LiteralPath $lio) {
  $existing = Get-Content -LiteralPath $lio -Raw -ErrorAction SilentlyContinue
}
foreach ($line in $need) {
  $key = $line.Split("=")[0]
  if ($existing -notmatch [regex]::Escape($key)) {
    Add-Content -LiteralPath $lio -Value $line -Encoding ASCII
  }
}
Write-Step "Enabled Manager AR file-sync commands in local_internal_options.conf"
Restart-Service -Name WazuhSvc -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "MSSP_WINDOWS_EDR_AR_OK"
Write-Host "Installed: kill / isolate / block-hash + auto-sync into $dest"
