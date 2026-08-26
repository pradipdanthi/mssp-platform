#Requires -RunAsAdministrator
# MSSP: keep Active Response scripts + mssp-ar.env current from Manager shared/.
# Works for appliance-local agents and direct/cloud (WAN) agents:
#   - Scripts: shared\ -> active-response\bin\
#   - Manager IP: ossec.conf <address> (appliance IP or public edge)
#   - Callback: public API by default (LAN + WAN); key from shared defaults or prior env
$ErrorActionPreference = "SilentlyContinue"

$DefaultCallbackUrl = "https://api.kevantic.com/v1/edr/actions/callback"
$DefaultControlPlaneIp = "192.168.0.201"

$roots = @(
  "${env:ProgramFiles(x86)}\ossec-agent",
  "$env:ProgramFiles\ossec-agent"
)
$root = $roots | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $root) { exit 0 }

$shared = Join-Path $root "shared"
$bin = Join-Path $root "active-response\bin"
$etc = Join-Path $root "etc"
$pd = Join-Path $env:ProgramData "mssp-edr-ar"

if (-not (Test-Path -LiteralPath $bin)) {
  New-Item -ItemType Directory -Path $bin -Force | Out-Null
}
New-Item -ItemType Directory -Path $pd -Force | Out-Null
New-Item -ItemType Directory -Path $etc -Force | Out-Null

$files = @(
  "mssp-isolate-host.cmd", "mssp-isolate-host.ps1",
  "mssp-kill-process.cmd", "mssp-kill-process.ps1",
  "mssp-block-hash.cmd", "mssp-block-hash.ps1",
  "Watch-MsspQuarantine.ps1",
  "Sync-MsspEdrAr.ps1"
)
foreach ($f in $files) {
  $src = Join-Path $shared $f
  if (Test-Path -LiteralPath $src) {
    Copy-Item -LiteralPath $src -Destination (Join-Path $bin $f) -Force
  }
}

# Keep ProgramData runner current (scheduled task + durable wodle target).
$selfShared = Join-Path $shared "Sync-MsspEdrAr.ps1"
$selfBin = Join-Path $bin "Sync-MsspEdrAr.ps1"
$selfPd = Join-Path $pd "Sync-MsspEdrAr.ps1"
if (Test-Path -LiteralPath $selfShared) {
  Copy-Item -LiteralPath $selfShared -Destination $selfPd -Force
} elseif (Test-Path -LiteralPath $selfBin) {
  Copy-Item -LiteralPath $selfBin -Destination $selfPd -Force
}
$watchShared = Join-Path $shared "Watch-MsspQuarantine.ps1"
if (Test-Path -LiteralPath $watchShared) {
  Copy-Item -LiteralPath $watchShared -Destination (Join-Path $pd "Watch-MsspQuarantine.ps1") -Force
}

function Get-MsspEnvMap([string]$Path) {
  $map = @{}
  if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return $map }
  Get-Content -LiteralPath $Path -ErrorAction SilentlyContinue | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
    $p = $_.Split('=', 2)
    if ($p.Count -ge 2) {
      $map[$p[0].Trim()] = $p[1].Trim().Trim('"').Trim("'")
    }
  }
  return $map
}

function Get-MsspManagerIp {
  $conf = Join-Path $etc "ossec.conf"
  if (-not (Test-Path -LiteralPath $conf)) { return "" }
  try {
    [xml]$xml = Get-Content -LiteralPath $conf -Raw
    $addr = $xml.ossec_config.client.server.address
    if ($addr -is [Array]) { $addr = $addr | Select-Object -First 1 }
    return [string]$addr
  } catch {
    $raw = Get-Content -LiteralPath $conf -Raw -ErrorAction SilentlyContinue
    if ($raw -match '<address>\s*([^<]+)\s*</address>') {
      return $Matches[1].Trim()
    }
  }
  return ""
}

$defaultsPath = Join-Path $shared "mssp-ar.env.defaults"
$keyFileShared = Join-Path $shared "mssp-callback.key"
$keyFileLocal = Join-Path $pd "mssp-callback.key"
$existingEnv = @(
  (Join-Path $etc "mssp-ar.env"),
  (Join-Path $bin "mssp-ar.env")
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

$defaults = Get-MsspEnvMap $defaultsPath
$prior = Get-MsspEnvMap $existingEnv

$manager = Get-MsspManagerIp
if (-not $manager) { $manager = $defaults['WAZUH_MANAGER_IP'] }
if (-not $manager) { $manager = $prior['WAZUH_MANAGER_IP'] }
if (-not $manager) { $manager = "192.168.0.211" }

$callbackUrl = $defaults['MSSP_CALLBACK_URL']
if (-not $callbackUrl) { $callbackUrl = $prior['MSSP_CALLBACK_URL'] }
if (-not $callbackUrl) { $callbackUrl = $DefaultCallbackUrl }

$controlPlane = $defaults['MSSP_CONTROL_PLANE_IP']
if (-not $controlPlane) { $controlPlane = $prior['MSSP_CONTROL_PLANE_IP'] }
if (-not $controlPlane) { $controlPlane = $DefaultControlPlaneIp }

$callbackKey = $defaults['MSSP_CALLBACK_KEY']
if (-not $callbackKey) { $callbackKey = $defaults['EDR_CALLBACK_API_KEY'] }
if (-not $callbackKey -and (Test-Path -LiteralPath $keyFileShared)) {
  $callbackKey = (Get-Content -LiteralPath $keyFileShared -Raw).Trim()
}
if (-not $callbackKey -and (Test-Path -LiteralPath $keyFileLocal)) {
  $callbackKey = (Get-Content -LiteralPath $keyFileLocal -Raw).Trim()
}
if (-not $callbackKey) { $callbackKey = $prior['MSSP_CALLBACK_KEY'] }
if (-not $callbackKey) { $callbackKey = $prior['EDR_CALLBACK_API_KEY'] }

$envLines = @(
  "WAZUH_MANAGER_IP=$manager",
  "MSSP_CONTROL_PLANE_IP=$controlPlane",
  "MSSP_CALLBACK_URL=$callbackUrl"
)
if ($callbackKey) {
  $envLines += "MSSP_CALLBACK_KEY=$callbackKey"
  try {
    Set-Content -LiteralPath $keyFileLocal -Value $callbackKey -Encoding ASCII -Force
  } catch {}
}

$envEtc = Join-Path $etc "mssp-ar.env"
$envBin = Join-Path $bin "mssp-ar.env"
$envLines | Set-Content -LiteralPath $envEtc -Encoding ASCII
$envLines | Set-Content -LiteralPath $envBin -Encoding ASCII

# Ensure scheduled task exists (idempotent) so sync works even without agent.conf wodle.
$taskName = "MSSP-EDR-AR-Sync"
$existingTask = schtasks.exe /Query /TN $taskName 2>$null
if (-not $existingTask -and (Test-Path -LiteralPath $selfPd)) {
  $tr = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$selfPd`""
  schtasks.exe /Create /TN $taskName /SC MINUTE /MO 1 /RU SYSTEM /RL HIGHEST /TR $tr /F | Out-Null
}

exit 0
