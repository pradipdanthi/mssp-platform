#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Install MSSP Windows EDR Active Response scripts (kill / isolate / block-hash).

.DESCRIPTION
  Day-one and remediation installer. Copies AR scripts into the endpoint agent
  active-response\bin folder. Safe to re-run (idempotent). Does not require Python.

.PARAMETER ManagerIp
  Wazuh Manager IP allowed during isolation (default 192.168.0.211).

.PARAMETER CallbackUrl
  Control-plane EDR callback URL (KB-091). Written into mssp-ar.env.

.PARAMETER CallbackKey
  Shared callback key (same as SOC sync key until per-execution tokens land).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\Install-MsspWindowsEdrAr.ps1
#>
[CmdletBinding()]
param(
  [string]$ManagerIp = "192.168.0.211",
  [string]$ControlPlaneIp = "192.168.0.201",
  [string]$CallbackUrl = "http://192.168.0.201:8000/v1/edr/actions/callback",
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
# Optional proof helper (not required on agent bin)
$optionalCopy = @("Test-MsspQuarantineProof.ps1")
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

$envOut = Join-Path $dest "mssp-ar.env"
$envLines = @(
  "WAZUH_MANAGER_IP=$ManagerIp",
  "MSSP_CONTROL_PLANE_IP=$ControlPlaneIp",
  "MSSP_CALLBACK_URL=$CallbackUrl"
)
if ($CallbackKey) {
  $envLines += "MSSP_CALLBACK_KEY=$CallbackKey"
  $keyState = "present"
} else {
  Write-Step "WARNING: CallbackKey empty - isolate will stay Dispatched (no applied=true callback)."
  $keyState = "MISSING"
}
$envLines | Set-Content -LiteralPath $envOut -Encoding ASCII
Write-Step "Wrote $envOut (callback URL set; key=$keyState)"

Write-Step "Restarting WazuhSvc..."
Restart-Service -Name WazuhSvc -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Get-Service -Name WazuhSvc | Format-List Name, Status

# Keep isolate scripts current from Manager shared/ (hold-until-unisolate).
$syncShared = Join-Path $agentRoot "shared\Sync-MsspEdrAr.ps1"
$syncLocal = Join-Path $Here "Sync-MsspEdrAr.ps1"
$syncDstDir = Join-Path $env:ProgramData "mssp-edr-ar"
New-Item -ItemType Directory -Path $syncDstDir -Force | Out-Null
$syncRun = Join-Path $syncDstDir "Sync-MsspEdrAr.ps1"
if (Test-Path -LiteralPath $syncLocal) {
  Copy-Item -LiteralPath $syncLocal -Destination $syncRun -Force
}
if (Test-Path -LiteralPath $syncShared) {
  Copy-Item -LiteralPath $syncShared -Destination $syncRun -Force
}
if (Test-Path -LiteralPath $syncRun) {
  & $syncRun
  $tr = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$syncRun`""
  schtasks.exe /Create /TN "MSSP-EDR-AR-Sync" /SC MINUTE /MO 1 /RU SYSTEM /RL HIGHEST /TR $tr /F | Out-Null
  Write-Step "Scheduled MSSP-EDR-AR-Sync (every 1 minute)"
}

# Same trust as Active Response: Manager may refresh AR files via agent.conf wodle.
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
Write-Host "Installed: kill / isolate / block-hash + quarantine watchdog into $dest"
