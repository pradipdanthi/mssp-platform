#Requires -RunAsAdministrator
# Deprecated one-shot helper. Prefer automatic Sync-MsspEdrAr (Manager shared + scheduled task).
# Kept for emergency manual refresh on already-enrolled WAN agents.
$ErrorActionPreference = "Stop"
$candidates = @(
  "$env:ProgramData\mssp-edr-ar\Sync-MsspEdrAr.ps1",
  "${env:ProgramFiles(x86)}\ossec-agent\shared\Sync-MsspEdrAr.ps1",
  "$env:ProgramFiles\ossec-agent\shared\Sync-MsspEdrAr.ps1",
  "${env:ProgramFiles(x86)}\ossec-agent\active-response\bin\Sync-MsspEdrAr.ps1",
  "$env:ProgramFiles\ossec-agent\active-response\bin\Sync-MsspEdrAr.ps1"
)
$sync = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $sync) {
  throw "Sync-MsspEdrAr.ps1 not found. Wait for Manager shared sync, or re-run Install-MsspWindowsEdrAr.ps1."
}
& $sync
Write-Host "MSSP_WAN_CALLBACK_OK (via Sync-MsspEdrAr)"
$envFile = @(
  "${env:ProgramFiles(x86)}\ossec-agent\etc\mssp-ar.env",
  "$env:ProgramFiles\ossec-agent\etc\mssp-ar.env"
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if ($envFile) { Get-Content -LiteralPath $envFile }
