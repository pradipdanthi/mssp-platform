"""KB-086: Build per-tenant endpoint agent install packages (ZIP)."""

from __future__ import annotations

import io
import os
import urllib.request
import zipfile
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse


DEFAULT_MANAGER = "192.168.0.211"
# Public edge (Oracle VPS) for remote/demo agents via nginx stream + WireGuard.
DEFAULT_WAN_MANAGER = "129.159.237.73"
DEFAULT_AGENT_VERSION = "4.14.6-1"

_LOCAL_OS_TYPES = frozenset({"windows", "linux", "all"})
_WAN_OS_TYPES = frozenset({"windows-wan", "linux-wan"})
_ALLOWED_OS_TYPES = _LOCAL_OS_TYPES | _WAN_OS_TYPES

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
    "mssp-ar.env.defaults",
)

_WINDOWS_AR_OPTIONAL_FILES = (
    "Test-MsspQuarantineProof.ps1",
    "agent.conf.mssp-edr-sync.xml",
)

_SYSMON_BIN_CANDIDATES = (
    Path(__file__).resolve().parents[1] / "endpoint_configs" / "Sysmon64.exe",
    Path("/app/app/endpoint_configs/Sysmon64.exe"),
    Path("/var/lib/mssp/sysmon-cache/Sysmon64.exe"),
    Path(__file__).resolve().parents[3] / ".cache" / "sysmon" / "Sysmon64.exe",
    Path("/opt/mssp-control/.cache/sysmon/Sysmon64.exe"),
    Path("/opt/mssp-control/deploy/windows-endpoint-telemetry/Sysmon64.exe"),
)

_LINUX_EXEC_RULES_CANDIDATES = (
    Path(__file__).resolve().parents[1]
    / "endpoint_configs"
    / "linux-edr-telemetry"
    / "mssp-exec.rules",
    Path("/app/app/endpoint_configs/linux-edr-telemetry/mssp-exec.rules"),
    Path("/opt/mssp-control/backend-api/app/endpoint_configs/linux-edr-telemetry/mssp-exec.rules"),
)

_LINUX_AR_DIR_CANDIDATES = (
    Path(__file__).resolve().parents[1] / "endpoint_configs" / "linux-edr-ar",
    Path("/app/app/endpoint_configs/linux-edr-ar"),
    Path(__file__).resolve().parents[2] / "deploy" / "wazuh-active-response",
    Path("/opt/mssp-control/deploy/wazuh-active-response"),
)

_LINUX_AR_FILES = (
    "mssp-isolate-host",
    "mssp-kill-process",
    "mssp-block-hash",
    "Sync-MsspEdrAr.sh",
)

_LINUX_AR_OPTIONAL_FILES = (
    "mssp-ar.env.defaults",
)

_DEFAULT_PUBLIC_CALLBACK_URL = "https://api.kevantic.com/v1/edr/actions/callback"
_CALLBACK_KEY_CANDIDATES = (
    Path("/run/secrets/soc_sync_api_key"),
    Path("/run/secrets/edr_callback_api_key"),
    Path("/opt/mssp-control/.secrets/soc_sync_api_key"),
    Path("/opt/mssp-control/.secrets/edr_callback_api_key"),
    Path(__file__).resolve().parents[3] / ".secrets" / "soc_sync_api_key",
    Path(__file__).resolve().parents[3] / ".secrets" / "edr_callback_api_key",
)

_LINUX_TELEMETRY_SH_CANDIDATES = (
    Path(__file__).resolve().parents[1]
    / "endpoint_configs"
    / "linux-edr-telemetry"
    / "install-mssp-linux-telemetry.sh",
    Path("/app/app/endpoint_configs/linux-edr-telemetry/install-mssp-linux-telemetry.sh"),
    Path(
        "/opt/mssp-control/backend-api/app/endpoint_configs/"
        "linux-edr-telemetry/install-mssp-linux-telemetry.sh"
    ),
)

_LINUX_EXEC_RULES_DEFAULT = """## MSSP Linux execve collection (collect != alert)
## Captures pid, ppid, comm, exe, uid/auid, cwd, command line (EXECVE a0..).
-a always,exit -F arch=b64 -S execve,execveat -F key=mssp_exec
-a always,exit -F arch=b32 -S execve,execveat -F key=mssp_exec
"""

_SYSMON_DOWNLOAD_URL = "https://download.sysinternals.com/files/Sysmon.zip"



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


def public_callback_url() -> str:
    raw = (os.getenv("EDR_PUBLIC_API_BASE") or os.getenv("MSSP_PUBLIC_API_BASE") or "").strip()
    if raw:
        return raw.rstrip("/") + "/v1/edr/actions/callback"
    override = (os.getenv("MSSP_CALLBACK_URL") or "").strip()
    return override or _DEFAULT_PUBLIC_CALLBACK_URL


def load_callback_key() -> str:
    env_key = (os.getenv("MSSP_CALLBACK_KEY") or os.getenv("EDR_CALLBACK_API_KEY") or "").strip()
    if env_key:
        return env_key
    for path in _CALLBACK_KEY_CANDIDATES:
        try:
            if path.is_file():
                return path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
    return ""


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
    for name in _WINDOWS_AR_OPTIONAL_FILES:
        path = root / name
        if path.is_file():
            out[name] = path.read_text(encoding="utf-8")
    return out


def load_linux_edr_ar_files() -> Dict[str, str]:
    """Return {filename: text} for Linux isolate/kill/block-hash AR pack."""
    root = _first_existing_dir(_LINUX_AR_DIR_CANDIDATES)
    if not root:
        raise FileNotFoundError("linux-edr-ar / wazuh-active-response not found")
    out: Dict[str, str] = {}
    for name in _LINUX_AR_FILES:
        path = root / name
        if not path.is_file():
            raise FileNotFoundError(f"Linux AR file missing: {path}")
        out[name] = path.read_text(encoding="utf-8")
    for name in _LINUX_AR_OPTIONAL_FILES:
        path = root / name
        if path.is_file():
            out[name] = path.read_text(encoding="utf-8")
        else:
            # Prefer windows defaults copy when linux tree is thin.
            win_root = _first_existing_dir(_WINDOWS_AR_DIR_CANDIDATES)
            alt = (win_root / name) if win_root else None
            if alt and alt.is_file():
                out[name] = alt.read_text(encoding="utf-8")
    return out


def _linux_edr_ar_install_script(manager: str) -> str:
    """Install Linux AR binaries into /var/ossec/active-response/bin + mssp-ar.env."""
    callback = public_callback_url()
    return f"""#!/usr/bin/env bash
set -euo pipefail
# MSSP Linux EDR Active Response installer (isolate / kill / block-hash)
MANAGER="{manager}"
CALLBACK_URL="${{MSSP_CALLBACK_URL:-{callback}}}"
CONTROL_PLANE_IP="${{MSSP_CONTROL_PLANE_IP:-192.168.0.201}}"
HERE="$(cd "$(dirname "${{BASH_SOURCE[0]:-$0}}")" && pwd)"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

DEST="/var/ossec/active-response/bin"
ETC="/var/ossec/etc"
STATE="/var/lib/mssp-edr-ar"
if [[ ! -d "$DEST" ]]; then
  echo "Wazuh agent active-response bin not found at $DEST" >&2
  exit 1
fi

for f in mssp-isolate-host mssp-kill-process mssp-block-hash; do
  if [[ ! -f "$HERE/$f" ]]; then
    echo "Missing $HERE/$f" >&2
    exit 1
  fi
  install -o root -g wazuh -m 0750 "$HERE/$f" "$DEST/$f"
done

if [[ -f "$HERE/Sync-MsspEdrAr.sh" ]]; then
  install -o root -g wazuh -m 0750 "$HERE/Sync-MsspEdrAr.sh" "$DEST/Sync-MsspEdrAr.sh"
  mkdir -p "$STATE"
  install -o root -g root -m 0750 "$HERE/Sync-MsspEdrAr.sh" "$STATE/Sync-MsspEdrAr.sh"
fi
if [[ -f "$HERE/mssp-ar.env.defaults" ]]; then
  install -o root -g wazuh -m 0640 "$HERE/mssp-ar.env.defaults" "$ETC/shared/mssp-ar.env.defaults" 2>/dev/null || true
fi

CALLBACK_KEY="${{MSSP_CALLBACK_KEY:-}}"
if [[ -z "$CALLBACK_KEY" && -f "$HERE/mssp-callback.key" ]]; then
  CALLBACK_KEY="$(tr -d '\\r\\n' < "$HERE/mssp-callback.key")"
fi

umask 077
{{
  echo "WAZUH_MANAGER_IP=$MANAGER"
  echo "MSSP_CONTROL_PLANE_IP=$CONTROL_PLANE_IP"
  echo "MSSP_CALLBACK_URL=$CALLBACK_URL"
  if [[ -n "$CALLBACK_KEY" ]]; then
    echo "MSSP_CALLBACK_KEY=$CALLBACK_KEY"
    mkdir -p "$STATE"
    printf '%s\\n' "$CALLBACK_KEY" > "$STATE/mssp-callback.key"
    chmod 600 "$STATE/mssp-callback.key"
  fi
}} > "$ETC/mssp-ar.env"
cp -f "$ETC/mssp-ar.env" "$DEST/mssp-ar.env" 2>/dev/null || true
chown root:wazuh "$ETC/mssp-ar.env" "$DEST/mssp-ar.env" 2>/dev/null || true
chmod 640 "$ETC/mssp-ar.env" "$DEST/mssp-ar.env" 2>/dev/null || true

if [[ -f "$STATE/Sync-MsspEdrAr.sh" ]]; then
  bash "$STATE/Sync-MsspEdrAr.sh" || true
  echo "* * * * * root /bin/bash $STATE/Sync-MsspEdrAr.sh >/dev/null 2>&1" > /etc/cron.d/mssp-edr-ar-sync
  chmod 644 /etc/cron.d/mssp-edr-ar-sync
fi

echo "OK: Linux EDR AR scripts installed into $DEST (auto-sync enabled)"
"""

def load_linux_exec_rules() -> str:
    path = _first_existing(_LINUX_EXEC_RULES_CANDIDATES)
    if path:
        return path.read_text(encoding="utf-8")
    return _LINUX_EXEC_RULES_DEFAULT


def load_linux_telemetry_installer() -> str:
    path = _first_existing(_LINUX_TELEMETRY_SH_CANDIDATES)
    if not path:
        raise FileNotFoundError("install-mssp-linux-telemetry.sh not found")
    return path.read_text(encoding="utf-8")


def resolve_sysmon_binary() -> Optional[Path]:
    """Return a local Sysmon64.exe if cached or freshly downloaded (best-effort)."""
    found = _first_existing(_SYSMON_BIN_CANDIDATES)
    if found:
        return found
    return _try_cache_sysmon_binary()


def _try_cache_sysmon_binary() -> Optional[Path]:
    dest_dirs = (
        Path("/var/lib/mssp/sysmon-cache"),
        Path("/opt/mssp-control/.cache/sysmon"),
        Path("/tmp/mssp-sysmon-cache"),
    )
    for folder in dest_dirs:
        candidate = folder / "Sysmon64.exe"
        if candidate.is_file() and candidate.stat().st_size > 10_000:
            return candidate
    skip = (os.getenv("MSSP_SKIP_SYSMON_CACHE_DOWNLOAD") or "").strip().lower()
    if skip in ("1", "true", "yes"):
        return None
    dest: Optional[Path] = None
    for folder in dest_dirs:
        try:
            folder.mkdir(parents=True, exist_ok=True)
            dest = folder
            break
        except OSError:
            continue
    if dest is None:
        return None
    zip_path = dest / "Sysmon.zip"
    timeout = float(os.getenv("MSSP_SYSMON_CACHE_TIMEOUT") or "12")
    try:
        req = urllib.request.Request(
            _SYSMON_DOWNLOAD_URL,
            headers={"User-Agent": "MSSP-agent-packager"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            zip_path.write_bytes(resp.read())
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            member = next((n for n in names if n.lower().endswith("sysmon64.exe")), None)
            if member is None:
                member = next((n for n in names if n.lower().endswith("sysmon.exe")), None)
            if member is None:
                return None
            data = zf.read(member)
        out = dest / "Sysmon64.exe"
        out.write_bytes(data)
        return out if out.stat().st_size > 10_000 else None
    except Exception:
        return None


def _linux_midlayer_suffix() -> str:
    """Fail-open auditd + Linux EDR AR hook appended after wazuh-agent enrollment."""
    body = load_linux_telemetry_installer()
    if body.startswith("#!"):
        body = body.split("\n", 1)[-1]
    return (
        "\n"
        "# Fail-open Linux mid-layer (auditd execve). Subshell so enrollment stays intact.\n"
        '_mssp_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"\n'
        'if [[ -n "${_mssp_script_dir}" && -f "${_mssp_script_dir}/install-mssp-linux-telemetry.sh" ]]; then\n'
        '  bash "${_mssp_script_dir}/install-mssp-linux-telemetry.sh" \\\n'
        '    || echo "[MSSP-TELEMETRY] WARN: Linux mid-layer telemetry skipped (agent still enrolled)" >&2\n'
        "else\n"
        "  bash -s <<'MSSP_LINUX_TELEMETRY' || echo \"[MSSP-TELEMETRY] WARN: Linux mid-layer telemetry skipped (agent still enrolled)\" >&2\n"
        f"{body.rstrip()}\n"
        "MSSP_LINUX_TELEMETRY\n"
        "fi\n"
        "# Fail-open Linux EDR AR (isolate/kill/block-hash).\n"
        'if [[ -n "${_mssp_script_dir}" && -f "${_mssp_script_dir}/edr-ar/install-mssp-linux-edr-ar.sh" ]]; then\n'
        '  bash "${_mssp_script_dir}/edr-ar/install-mssp-linux-edr-ar.sh" \\\n'
        '    || echo "[MSSP-EDR-AR] WARN: Linux EDR AR install skipped (agent still enrolled)" >&2\n'
        "fi\n"
    )


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


def wan_manager_address() -> str:
    """Public enrollment edge for WAN / remote-demo agent packages."""
    raw = (os.getenv("WAZUH_WAN_MANAGER_ADDRESS") or "").strip()
    return raw or DEFAULT_WAN_MANAGER


def is_wan_os_type(os_type: str) -> bool:
    return (os_type or "").strip().lower() in _WAN_OS_TYPES


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
    os_type: windows | linux | all | windows-wan | linux-wan
    customer_facing: soften README/INSTALL wording (no engine product names).
    manager: optional override (appliance LAN IP for local packages).
             Ignored for *-wan types — WAN always uses wan_manager_address().
    """
    os_key = (os_type or "").strip().lower()
    if os_key not in _ALLOWED_OS_TYPES:
        raise ValueError(
            "os_type must be windows, linux, all, windows-wan, or linux-wan"
        )

    wan = os_key in _WAN_OS_TYPES
    base_os = os_key.replace("-wan", "") if wan else os_key
    if wan:
        manager = wan_manager_address()
    else:
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
                wan=wan,
            ),
        )
        channel = "wan" if wan else "local"
        zf.writestr(
            "tenant.env",
            (
                f"TENANT_SHORT_CODE={code}\n"
                f"TENANT_NAME={tenant_name}\n"
                f"WAZUH_MANAGER={manager}\n"
                f"WAZUH_REGISTRATION_SERVER={manager}\n"
                f"WAZUH_AGENT_GROUP={group}\n"
                f"WAZUH_AGENT_VERSION={version}\n"
                f"MSSP_PACKAGE_CHANNEL={channel}\n"
            ),
        )
        if base_os in ("linux", "all"):
            zf.writestr("linux/install-linux-agent.sh", _linux_script(manager, group, version, code))
            zf.writestr("linux/mssp-exec.rules", load_linux_exec_rules())
            zf.writestr(
                "linux/install-mssp-linux-telemetry.sh",
                load_linux_telemetry_installer(),
            )
            try:
                linux_ar = load_linux_edr_ar_files()
            except FileNotFoundError as exc:
                raise ValueError(
                    "Linux package requires isolate/kill/block-hash AR scripts"
                ) from exc
            for name, text in linux_ar.items():
                zf.writestr(f"linux/edr-ar/{name}", text)
            cb_key = load_callback_key()
            if cb_key:
                zf.writestr("linux/edr-ar/mssp-callback.key", cb_key + "\n")
            zf.writestr(
                "linux/edr-ar/install-mssp-linux-edr-ar.sh",
                _linux_edr_ar_install_script(manager),
            )
            zf.writestr(
                "linux/INSTALL.txt",
                _linux_install_txt(
                    group, manager, customer_facing=customer_facing, wan=wan
                ),
            )
        if base_os in ("windows", "all"):
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
            sysmon_bin = resolve_sysmon_binary()
            if sysmon_bin is not None:
                zf.write(sysmon_bin, "windows/Sysmon64.exe")
            for name, text in ar_files.items():
                zf.writestr(f"windows/edr-ar/{name}", text)
            cb_key = load_callback_key()
            if cb_key:
                zf.writestr("windows/edr-ar/mssp-callback.key", cb_key + "\n")
            zf.writestr(
                "windows/install-windows-agent.ps1",
                _windows_script(manager, group, version, code),
            )
            zf.writestr(
                "windows/INSTALL.txt",
                _windows_install_txt(
                    group, manager, customer_facing=customer_facing, wan=wan
                ),
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
    wan: bool = False,
) -> str:
    channel_label = "Remote / WAN (demo)" if wan else "Local / LAN"
    channel_note = (
        "This package is for endpoints outside the office LAN (remote demo).\n"
        "It enrolls through the public enrollment edge - do not use it on\n"
        "office/LAN computers that should use the local package.\n"
        if wan
        else ""
    )
    if customer_facing:
        return f"""Endpoint monitoring agent package
=================================

Organization: {tenant_name}
Customer code: {short_code}
Package channel: {channel_label}
Enrollment server: {manager}
Auto-assigned bucket: {group}

{channel_note}This package installs the endpoint monitoring agent and enrolls the device
into your organization's bucket automatically.

Linux
-----
1. Copy the linux/ folder to the computer.
2. Run ONLY this command (do not paste the notes below it):
     sudo bash linux/install-linux-agent.sh
   Note: that script also enables process-execution telemetry.
3. Confirm the device appears under Assets in your security portal.

Windows
-------
1. Copy the windows/ folder to the computer.
2. Open PowerShell as Administrator.
3. Run ONLY this one line (do not paste any notes after it):
     powershell -ExecutionPolicy Bypass -File .\\windows\\install-windows-agent.ps1
   Note: the script also enables process telemetry and EDR response actions.
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
Package channel: {channel_label}
Manager: {manager}
Auto bucket (agent group): {group}

{channel_note}This package installs the endpoint security agent and enrolls it into the
correct customer bucket automatically. You do not need to pick the group
manually if you use the scripts below.

Linux
-----
1. Copy the linux/ folder to the endpoint.
2. Run:  sudo bash linux/install-linux-agent.sh
   This also installs auditd execve collection and wires the agent to
   /var/log/audit/audit.log (collect != alert).
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


def _linux_install_txt(
    group: str, manager: str, *, customer_facing: bool = False, wan: bool = False
) -> str:
    channel = "Remote / WAN (demo)" if wan else "Local / LAN"
    if customer_facing:
        return (
            "Run as root:\n"
            "  sudo bash install-linux-agent.sh\n\n"
            "Also enables process-execution telemetry on this computer.\n\n"
            f"Package channel: {channel}\n"
            f"Enrollment server: {manager}\n"
            f"Organization bucket: {group}\n"
        )
    return (
        "Run as root:\n"
        "  sudo bash install-linux-agent.sh\n\n"
        "Also installs auditd execve collection and adds a Wazuh <localfile>\n"
        "reader for /var/log/audit/audit.log before restarting the agent.\n\n"
        f"Channel: {channel}\n"
        f"Manager: {manager}\n"
        f"Group:   {group}\n"
    )


def _windows_install_txt(
    group: str, manager: str, *, customer_facing: bool = False, wan: bool = False
) -> str:
    channel = "Remote / WAN (demo)" if wan else "Local / LAN"
    if customer_facing:
        return (
            "Run PowerShell as Administrator:\n"
            "  powershell -ExecutionPolicy Bypass -File .\\install-windows-agent.ps1\n\n"
            "The installer also enables required process telemetry on this computer.\n\n"
            f"Package channel: {channel}\n"
            f"Enrollment server: {manager}\n"
            f"Organization bucket: {group}\n"
        )
    return (
        "Run PowerShell as Administrator:\n"
        "  powershell -ExecutionPolicy Bypass -File .\\install-windows-agent.ps1\n\n"
        "Also installs/updates Sysmon (filtered), enables 4688+cmdline auditing,\n"
        "and wires ossec.conf localfile channels. The package prefers Sysmon64.exe\n"
        "in this folder (offline); it downloads Sysinternals only if that file is\n"
        "missing and the host has network. Re-run Enable-MsspWindowsTelemetry.ps1\n"
        "alone if the agent is already installed.\n\n"
        f"Channel: {channel}\n"
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
""" + _linux_midlayer_suffix()


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
$EdrArgs = @{{
  ManagerIp = $Manager
  CallbackUrl = "https://api.kevantic.com/v1/edr/actions/callback"
}}
$CbKeyFile = Join-Path $EdrArDir "mssp-callback.key"
if (Test-Path -LiteralPath $CbKeyFile) {{
  $EdrArgs["CallbackKey"] = (Get-Content -LiteralPath $CbKeyFile -Raw).Trim()
}}
& $EdrArInstaller @EdrArgs

Get-Service -Name WazuhSvc | Format-List Name, Status
Write-Host "OK: agent installed for group $Group (tenant {short_code}) with telemetry + EDR AR"
"""
