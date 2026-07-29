#!/usr/bin/env bash
# Remove Wazuh agent from Windows endpoint lab (VM 104) via WinRM.
# Requires: WINRM_PASSWORD (Administrator), optional WINRM_HOST (default 192.168.0.214)
set -uo pipefail
cd /opt/mssp-control

HOST="${WINRM_HOST:-192.168.0.214}"
USER="${WINRM_USER:-Administrator}"

if [[ -z "${WINRM_PASSWORD:-}" ]]; then
  echo "Set WINRM_PASSWORD to the Windows Administrator password, then re-run." >&2
  exit 1
fi

ssh -o BatchMode=yes automation "WINRM_HOST='${HOST}' WINRM_USER='${USER}' WINRM_PASSWORD='${WINRM_PASSWORD}' bash -s" <<'REMOTE'
set -euo pipefail
cat > /tmp/openssl-legacy.cnf <<'CNF'
openssl_conf = openssl_init
[openssl_init]
providers = provider_sect
[provider_sect]
default = default_sect
legacy = legacy_sect
[default_sect]
activate = 1
[legacy_sect]
activate = 1
CNF
export OPENSSL_CONF=/tmp/openssl-legacy.cnf
python3 - <<'PY'
import os
import sys
import winrm

host = os.environ["WINRM_HOST"]
user = os.environ["WINRM_USER"]
password = os.environ["WINRM_PASSWORD"]

session = winrm.Session(
    f"http://{host}:5985/wsman",
    auth=(user, password),
    transport="ntlm",
    server_cert_validation="ignore",
    read_timeout_sec=900,
    operation_timeout_sec=850,
)

ps = r'''
$ErrorActionPreference = "Stop"
function Get-WazuhUninstall {
  $paths = @(
    "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
  )
  foreach ($pattern in $paths) {
    $items = Get-ItemProperty $pattern -ErrorAction SilentlyContinue |
      Where-Object { $_.DisplayName -like "*Wazuh*" }
    if ($items) { return $items | Select-Object -First 1 }
  }
  return $null
}

$svc = Get-Service -Name WazuhSvc -ErrorAction SilentlyContinue
if ($svc) {
  Write-Output "Stopping WazuhSvc (was $($svc.Status))"
  Stop-Service -Name WazuhSvc -Force -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 2
} else {
  Write-Output "WazuhSvc service not found (may already be removed)"
}

$app = Get-WazuhUninstall
if (-not $app) {
  Write-Output "No Wazuh entry in Add/Remove Programs"
} else {
  Write-Output ("Found: " + $app.DisplayName + " v" + $app.DisplayVersion)
  $guid = $app.PSChildName
  if ($guid -match '^\{[0-9A-Fa-f-]+\}$') {
    Write-Output "Uninstalling via msiexec /x $guid"
    $p = Start-Process -FilePath "msiexec.exe" -ArgumentList @("/x", $guid, "/qn", "/norestart") -Wait -PassThru
    Write-Output ("msiexec_exit=" + $p.ExitCode)
    if ($p.ExitCode -ne 0 -and $p.ExitCode -ne 1605) {
      throw "msiexec uninstall failed $($p.ExitCode)"
    }
  } elseif ($app.UninstallString) {
    Write-Output ("Running UninstallString: " + $app.UninstallString)
    cmd.exe /c $app.UninstallString
  } else {
    throw "Could not determine uninstall command"
  }
}

$left = Get-WazuhUninstall
if ($left) { throw "Wazuh still listed after uninstall" }

$paths = @(
  "${env:ProgramFiles(x86)}\ossec-agent",
  "$env:ProgramFiles\ossec-agent"
)
foreach ($dir in $paths) {
  if (Test-Path $dir) {
    Write-Output "Removing leftover folder $dir"
    Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue
  }
}

$svc2 = Get-Service -Name WazuhSvc -ErrorAction SilentlyContinue
if ($svc2) { throw "WazuhSvc still present" }
Write-Output "WAZUH_AGENT_UNINSTALLED_OK"
'''

r = session.run_ps(ps)
out = (r.std_out or b"").decode("utf-8", errors="replace")
err = (r.std_err or b"").decode("utf-8", errors="replace")
print(out)
if err.strip():
    print(err, file=sys.stderr)
if r.status_code != 0 or "WAZUH_AGENT_UNINSTALLED_OK" not in out:
    sys.exit(1)
print("REMOTE_OK")
PY
REMOTE
