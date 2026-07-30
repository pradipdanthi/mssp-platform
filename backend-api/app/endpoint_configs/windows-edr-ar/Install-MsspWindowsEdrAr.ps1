#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Install MSSP Windows EDR Active Response scripts (kill / isolate / block-hash).

.DESCRIPTION
  Day-one and remediation installer. Copies AR scripts into the endpoint agent
  active-response\bin folder. Safe to re-run (idempotent). Does not require Python.

.PARAMETER ManagerIp
  Wazuh Manager IP allowed during isolation (default 192.168.0.211).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\Install-MsspWindowsEdrAr.ps1
#>
[CmdletBinding()]
param(
  [string]$ManagerIp = "192.168.0.211"
)

$ErrorActionPreference = "Stop"

# Fingerprint — refuse to run if this file was overwritten with another AR script.
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
  "mssp-block-hash.cmd", "mssp-block-hash.ps1"
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
foreach ($f in $optionalCopy) {
  $src = Join-Path $Here $f
  if (Test-Path -LiteralPath $src) {
    Copy-Item -LiteralPath $src -Destination (Join-Path $dest $f) -Force
  }
}

$envOut = Join-Path $dest "mssp-ar.env"
"WAZUH_MANAGER_IP=$ManagerIp" | Set-Content -LiteralPath $envOut -Encoding ASCII
Write-Step "Wrote $envOut"

Write-Step "Restarting WazuhSvc..."
Restart-Service -Name WazuhSvc -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Get-Service -Name WazuhSvc | Format-List Name, Status

Write-Host ""
Write-Host "MSSP_WINDOWS_EDR_AR_OK"
Write-Host "Installed: kill / isolate / block-hash into $dest"
