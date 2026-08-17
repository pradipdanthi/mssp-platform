"""KB-086: Build per-tenant endpoint agent install packages (ZIP)."""

from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse


DEFAULT_MANAGER = "192.168.0.211"
DEFAULT_AGENT_VERSION = "4.14.6-1"

_SYSMON_CONFIG_CANDIDATES = (
    Path(__file__).resolve().parents[1] / "endpoint_configs" / "sysmon-windows-baseline.xml",
    Path("/app/app/endpoint_configs/sysmon-windows-baseline.xml"),
    Path("/opt/mssp-control/templates/endpoint-configs/sysmon-windows-baseline.xml"),
    Path("/opt/mssp-control/deploy/windows-endpoint-telemetry/sysmon-windows-baseline.xml"),
)

_TELEMETRY_PS1_CANDIDATES = (
    Path(__file__).resolve().parents[1] / "endpoint_configs" / "Enable-MsspWindowsTelemetry.ps1",
    Path("/app/app/endpoint_configs/Enable-MsspWindowsTelemetry.ps1"),
    Path("/opt/mssp-control/deploy/windows-endpoint-telemetry/Enable-MsspWindowsTelemetry.ps1"),
    Path("/opt/mssp-control/scripts/bootstrap_windows_telemetry.ps1"),
    Path("/opt/mssp-control/templates/endpoint-configs/Enable-MsspWindowsTelemetry.ps1"),
)

_WINDOWS_AR_DIR_CANDIDATES = (
    Path(__file__).resolve().parents[1] / "endpoint_configs" / "windows-edr-ar",
    Path("/app/app/endpoint_configs/windows-edr-ar"),
    Path(__file__).resolve().parents[2] / "deploy" / "wazuh-active-response" / "windows",
    Path("/opt/mssp-control/deploy/wazuh-active-response/windows"),
)

_WINDOWS_AR_FILES = (
    "mssp-kill-process.cmd",
    "mssp-kill-process.ps1",
    "mssp-isolate-host.cmd",
    "mssp-isolate-host.ps1",
    "mssp-block-hash.cmd",
    "mssp-block-hash.ps1",
    "Install-MsspWindowsEdrAr.ps1",
    "Sync-MsspEdrAr.ps1",
    "Watch-MsspQuarantine.ps1",
)


def _first_existing(paths: tuple[Path, ...]) -> Optional[Path]:
    for path in paths:
        if path.is_file():
            return path
    return None


def _first_existing_dir(paths: tuple[Path, ...]) -> Optional[Path]:
    for path in paths:
        if path.is_dir():
            return path
    return None


def load_sysmon_baseline_xml() -> str:
    path = _first_existing(_SYSMON_CONFIG_CANDIDATES)
    if not path:
        raise FileNotFoundError("sysmon-windows-baseline.xml not found")
    return path.read_text(encoding="utf-8")


def load_windows_telemetry_script() -> str:
    path = _first_existing(_TELEMETRY_PS1_CANDIDATES)
    if not path:
        raise FileNotFoundError("Enable-MsspWindowsTelemetry.ps1 / bootstrap not found")
    return path.read_text(encoding="utf-8")


def load_windows_edr_ar_files() -> Dict[str, str]:
    """Return {filename: text} for Windows kill/isolate/block-hash AR pack."""
    root = _first_existing_dir(_WINDOWS_AR_DIR_CANDIDATES)
    if not root:
        raise FileNotFoundError("deploy/wazuh-active-response/windows not found")
    out: Dict[str, str] = {}
    for name in _WINDOWS_AR_FILES:
        path = root / name
        if not path.is_file():
            raise FileNotFoundError(f"Windows AR file missing: {path}")
        out[name] = path.read_text(encoding="utf-8")
    return out


def manager_address() -> str:
    raw = (os.getenv("WAZUH_MANAGER_ADDRESS") or "").strip()
    if raw:
        return raw
    api = (os.getenv("WAZUH_API_URL") or "").strip()
    if api:
        host = urlparse(api).hostname
        if host:
            return host
    return DEFAULT_MANAGER


def agent_version() -> str:
    return (os.getenv("WAZUH_AGENT_PACKAGE_VERSION") or DEFAULT_AGENT_VERSION).strip()


def build_linux_install_script(
    *,
    short_code: str,
    wazuh_agent_group: str,
    manager: Optional[str] = None,
) -> str:
    """Standalone Linux installer script (also embedded in ZIP packages)."""
    code = short_code.strip().upper()
    group = (wazuh_agent_group or f"tenant_{code}").strip()
    mgr = (manager or "").strip() or manager_address()
    return _linux_script(mgr, group, agent_version(), code)


def build_agent_package_zip(
    *,
    tenant_name: str,
    short_code: str,
    wazuh_agent_group: str,
    os_type: str,
    customer_facing: bool = False,
    manager: Optional[str] = None,
) -> Tuple[bytes, str]:
    """
    Returns (zip_bytes, filename).
    os_type: windows | linux | all
    customer_facing: soften README/INSTALL wording (no engine product names).
    manager: optional override (appliance LAN IP for appliance tenants).
    """
    os_key = (os_type or "").strip().lower()
    if os_key not in ("windows", "linux", "all"):
        raise ValueError("os_type must be windows, linux, or all")

    manager = (manager or "").strip() or manager_address()
    version = agent_version()
    code = short_code.strip().upper()
    group = (wazuh_agent_group or f"tenant_{code}").strip()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "README.txt",
            _readme(
                tenant_name=tenant_name,
                short_code=code,
                group=group,
                manager=manager,
                customer_facing=customer_facing,
            ),
        )
        zf.writestr(
            "tenant.env",
            (
                f"TENANT_SHORT_CODE={code}\n"
                f"TENANT_NAME={tenant_name}\n"
                f"WAZUH_MANAGER={manager}\n"
                f"WAZUH_REGISTRATION_SERVER={manager}\n"
                f"WAZUH_AGENT_GROUP={group}\n"
                f"WAZUH_AGENT_VERSION={version}\n"
            ),
        )
        if os_key in ("linux", "all"):
            zf.writestr("linux/install-linux-agent.sh", _linux_script(manager, group, version, code))
            zf.writestr(
                "linux/INSTALL.txt",
                _linux_install_txt(group, manager, customer_facing=customer_facing),
            )
        if os_key in ("windows", "all"):
            try:
                sysmon_xml = load_sysmon_baseline_xml()
                telemetry_ps1 = load_windows_telemetry_script()
                ar_files = load_windows_edr_ar_files()
            except FileNotFoundError as exc:
                raise ValueError(
                    "Windows package requires Sysmon baseline + telemetry + EDR AR scripts"
                ) from exc
            zf.writestr("windows/sysmon-windows-baseline.xml", sysmon_xml)
            zf.writestr("windows/Enable-MsspWindowsTelemetry.ps1", telemetry_ps1)
            for name, text in ar_files.items():
                zf.writestr(f"windows/edr-ar/{name}", text)
            zf.writestr(
                "windows/install-windows-agent.ps1",
                _windows_script(manager, group, version, code),
            )
            zf.writestr(
                "windows/INSTALL.txt",
                _windows_install_txt(group, manager, customer_facing=customer_facing),
            )

    filename = f"mssp-agent-{code.lower()}-{os_key}.zip"
    return buf.getvalue(), filename


def _readme(
    *,
    tenant_name: str,
    short_code: str,
    group: str,
    manager: str,
    customer_facing: bool,
) -> str:
    if customer_facing:
        return f"""Endpoint monitoring agent package
=================================

Organization: {tenant_name}
Customer code: {short_code}
Enrollment server: {manager}
Auto-assigned bucket: {group}

This package installs the endpoint monitoring agent and enrolls the device
into your organization's bucket automatically.

Linux
-----
1. Copy the linux/ folder to the computer.
2. Run:  sudo bash linux/install-linux-agent.sh
3. Confirm the device appears under Assets in your security portal.

Windows
-------
1. Copy the windows/ folder to the computer.
2. Open PowerShell as Administrator.
3. Run:  powershell -ExecutionPolicy Bypass -File .\\windows\\install-windows-agent.ps1
   (Installs the agent, enables process telemetry prerequisites, and wires log channels.)
4. Confirm the device appears under Assets in your security portal.

Notes
-----
- Keep this package private - it is specific to your organization.
- Process telemetry is filtered collection for investigation - not an alert for every process.
- After install, open Assets in the portal and refresh; the computer should
  appear under Protected assets within a minute.
- Ask your security provider if you need help with installation.
"""
    return f"""MSSP endpoint agent package
===========================

Customer: {tenant_name}
Short code: {short_code}
Manager: {manager}
Auto bucket (agent group): {group}

This package installs the endpoint security agent and enrolls it into the
correct customer bucket automatically. You do not need to pick the group
manually if you use the scripts below.

Linux
-----
1. Copy the linux/ folder to the endpoint.
2. Run:  sudo bash linux/install-linux-agent.sh
3. Confirm the agent is Active on the SOC platform.

Windows
-------
1. Copy the windows/ folder to the endpoint.
2. Open PowerShell as Administrator.
3. Run:  powershell -ExecutionPolicy Bypass -File .\\windows\\install-windows-agent.ps1
   This also installs/updates filtered Sysmon telemetry, enables process-creation
   auditing with command lines, and adds agent log channels (Sysmon + Event 4688).
4. Confirm the agent is Active on the SOC platform.

Notes
-----
- Keep this package private (it targets a specific customer bucket).
- Telemetry prerequisites are required for process-tree / EDR deep dive.
- Collection != alert: manager rules decide what becomes SOC alerts.
"""


def _linux_install_txt(group: str, manager: str, *, customer_facing: bool = False) -> str:
    if customer_facing:
        return (
            "Run as root:\n"
            "  sudo bash install-linux-agent.sh\n\n"
            f"Enrollment server: {manager}\n"
            f"Organization bucket: {group}\n"
        )
    return (
        "Run as root:\n"
        "  sudo bash install-linux-agent.sh\n\n"
        f"Manager: {manager}\n"
        f"Group:   {group}\n"
    )


def _windows_install_txt(group: str, manager: str, *, customer_facing: bool = False) -> str:
    if customer_facing:
        return (
            "Run PowerShell as Administrator:\n"
            "  powershell -ExecutionPolicy Bypass -File .\\install-windows-agent.ps1\n\n"
            "The installer also enables required process telemetry on this computer.\n\n"
            f"Enrollment server: {manager}\n"
            f"Organization bucket: {group}\n"
        )
    return (
        "Run PowerShell as Administrator:\n"
        "  powershell -ExecutionPolicy Bypass -File .\\install-windows-agent.ps1\n\n"
        "Also installs/updates Sysmon (filtered), enables 4688+cmdline auditing,\n"
        "and wires ossec.conf localfile channels. Re-run Enable-MsspWindowsTelemetry.ps1\n"
        "alone if the agent is already installed.\n\n"
        f"Manager: {manager}\n"
        f"Group:   {group}\n"
    )


def _linux_script(manager: str, group: str, version: str, short_code: str) -> str:
    # Keep shell escaping simple - values are controlled (short_code alphanumeric).
    return f"""#!/usr/bin/env bash
set -euo pipefail
# MSSP Linux endpoint agent installer - tenant {short_code}
MANAGER="{manager}"
GROUP="{group}"
VERSION="{version}"
AGENT_NAME="${{WAZUH_AGENT_NAME:-$(hostname -s)}}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

export WAZUH_MANAGER="$MANAGER"
export WAZUH_REGISTRATION_SERVER="$MANAGER"
export WAZUH_AGENT_GROUP="$GROUP"
export WAZUH_AGENT_NAME="$AGENT_NAME"

if command -v apt-get >/dev/null 2>&1; then
  apt-get update -y
  apt-get install -y curl apt-transport-https gnupg lsb-release
  curl -s https://packages.wazuh.com/key/GPG-KEY-WAZUH | gpg --no-default-keyring --keyring gnupg-ring:/usr/share/keyrings/wazuh.gpg --import
  chmod 644 /usr/share/keyrings/wazuh.gpg
  echo "deb [signed-by=/usr/share/keyrings/wazuh.gpg] https://packages.wazuh.com/4.x/apt/ stable main" > /etc/apt/sources.list.d/wazuh.list
  apt-get update -y
  WAZUH_MANAGER="$MANAGER" WAZUH_AGENT_GROUP="$GROUP" WAZUH_AGENT_NAME="$AGENT_NAME" \\
    apt-get install -y "wazuh-agent=${{VERSION}}"
elif command -v dnf >/dev/null 2>&1 || command -v yum >/dev/null 2>&1; then
  PKG_MGR="$(command -v dnf || command -v yum)"
  rpm --import https://packages.wazuh.com/key/GPG-KEY-WAZUH
  cat > /etc/yum.repos.d/wazuh.repo <<'EOF'
[wazuh]
gpgcheck=1
gpgkey=https://packages.wazuh.com/key/GPG-KEY-WAZUH
enabled=1
name=Wazuh repository
baseurl=https://packages.wazuh.com/4.x/yum/
protect=1
EOF
  WAZUH_MANAGER="$MANAGER" WAZUH_AGENT_GROUP="$GROUP" WAZUH_AGENT_NAME="$AGENT_NAME" \\
    "$PKG_MGR" install -y "wazuh-agent-${{VERSION}}"
else
  echo "Unsupported Linux package manager" >&2
  exit 1
fi

systemctl daemon-reload || true
systemctl enable wazuh-agent
systemctl restart wazuh-agent
sleep 2
/var/ossec/bin/wazuh-control status || true
echo "OK: agent installed for group $GROUP (tenant {short_code})"
"""


def _windows_script(manager: str, group: str, version: str, short_code: str) -> str:
    msi = f"https://packages.wazuh.com/4.x/windows/wazuh-agent-{version}.msi"
    return f"""#Requires -RunAsAdministrator
# MSSP Windows endpoint agent installer - tenant {short_code}
# Installs agent + process telemetry prerequisites (Sysmon / audit / localfile).
$ErrorActionPreference = "Stop"
$Manager = "{manager}"
$Group = "{group}"
$Version = "{version}"
$MsiUrl = "{msi}"
$AgentName = if ($env:WAZUH_AGENT_NAME) {{ $env:WAZUH_AGENT_NAME }} else {{ $env:COMPUTERNAME }}
$MsiPath = Join-Path $env:TEMP ("wazuh-agent-" + $Version + ".msi")
$Here = $PSScriptRoot
if (-not $Here) {{ $Here = Split-Path -Parent $MyInvocation.MyCommand.Path }}

Write-Host "Downloading agent $Version ..."
Invoke-WebRequest -Uri $MsiUrl -OutFile $MsiPath

Write-Host "Installing agent into group $Group ..."
$msiArgs = "/i `"$MsiPath`" /q WAZUH_MANAGER=`"$Manager`" WAZUH_REGISTRATION_SERVER=`"$Manager`" WAZUH_AGENT_GROUP=`"$Group`" WAZUH_AGENT_NAME=`"$AgentName`""
$p = Start-Process -FilePath "msiexec.exe" -ArgumentList $msiArgs -Wait -PassThru
if ($p.ExitCode -ne 0) {{
  throw "msiexec failed with exit code $($p.ExitCode)"
}}

Start-Service -Name WazuhSvc -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

$Telemetry = Join-Path $Here "Enable-MsspWindowsTelemetry.ps1"
$SysmonCfg = Join-Path $Here "sysmon-windows-baseline.xml"
if (-not (Test-Path -LiteralPath $Telemetry)) {{
  throw "Missing Enable-MsspWindowsTelemetry.ps1 next to this installer"
}}
if (-not (Test-Path -LiteralPath $SysmonCfg)) {{
  throw "Missing sysmon-windows-baseline.xml next to this installer"
}}
Write-Host "Configuring Windows process telemetry prerequisites ..."
& $Telemetry -SysmonConfigPath $SysmonCfg

$EdrArDir = Join-Path $Here "edr-ar"
$EdrArInstaller = Join-Path $EdrArDir "Install-MsspWindowsEdrAr.ps1"
if (-not (Test-Path -LiteralPath $EdrArInstaller)) {{
  throw "Missing edr-ar/Install-MsspWindowsEdrAr.ps1 (kill/isolate/block-hash pack)"
}}
Write-Host "Installing Windows EDR response actions (kill / isolate / block-hash) ..."
& $EdrArInstaller -ManagerIp $Manager

Get-Service -Name WazuhSvc | Format-List Name, Status
Write-Host "OK: agent installed for group $Group (tenant {short_code}) with telemetry + EDR AR"
"""
