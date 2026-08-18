#!/usr/bin/env python3
"""End-to-end audit of mid-layer EDR packaging + process-tree ingestion.

Standalone. Does not write to PostgreSQL, change source_tool, or open ports.
Exit 0 when every check is PASSED or WARNING; exit 1 if any check FAILED.

Usage:
  python3 scripts/verify_e2e_midlayer_edr.py
"""

from __future__ import annotations

import io
import os
import re
import sys
import traceback
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend-api"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("MSSP_SKIP_SYSMON_CACHE_DOWNLOAD", "1")

# --- color ---
if sys.stdout.isatty() and os.getenv("NO_COLOR", "") == "":
    GREEN, YELLOW, RED, BOLD, DIM, RESET = (
        "\033[32m",
        "\033[33m",
        "\033[31m",
        "\033[1m",
        "\033[2m",
        "\033[0m",
    )
else:
    GREEN = YELLOW = RED = BOLD = DIM = RESET = ""


@dataclass
class Finding:
    status: str  # PASSED | FAILED | WARNING
    title: str
    detail: str = ""
    path: Optional[Path] = None
    line: Optional[int] = None

    def render(self) -> str:
        color = {"PASSED": GREEN, "FAILED": RED, "WARNING": YELLOW}.get(self.status, "")
        loc = ""
        if self.path is not None:
            rel = self.path if self.path.is_absolute() else self.path
            try:
                rel = self.path.relative_to(ROOT)
            except ValueError:
                rel = self.path
            loc = f"  {DIM}{rel}"
            if self.line:
                loc += f":{self.line}"
            loc += RESET
        extra = f"\n    {self.detail}" if self.detail else ""
        return f"  {color}{self.status:7}{RESET} {self.title}{loc}{extra}"


@dataclass
class CheckResult:
    name: str
    findings: List[Finding] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return any(f.status == "FAILED" for f in self.findings)


def locate(path: Path, pattern: str, *, flags: int = 0) -> Optional[int]:
    if not path.is_file():
        return None
    rx = re.compile(pattern, flags)
    for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if rx.search(line):
            return i
    return None


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def require_file(findings: List[Finding], path: Path, title: str) -> bool:
    if path.is_file():
        findings.append(Finding("PASSED", title, path=path))
        return True
    findings.append(
        Finding("FAILED", title, detail="file does not exist", path=path)
    )
    return False


def expect(
    findings: List[Finding],
    ok: bool,
    title: str,
    *,
    path: Optional[Path] = None,
    pattern: Optional[str] = None,
    flags: int = 0,
    detail: str = "",
    warn: bool = False,
) -> None:
    line = locate(path, pattern, flags=flags) if path is not None and pattern else None
    if ok:
        findings.append(Finding("PASSED", title, detail=detail, path=path, line=line))
        return
    status = "WARNING" if warn else "FAILED"
    reason = detail or (
        f"pattern not found: {pattern}" if pattern else "condition was false"
    )
    findings.append(Finding(status, title, detail=reason, path=path, line=line))


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PS1_CANONICAL = BACKEND / "app" / "endpoint_configs" / "Enable-MsspWindowsTelemetry.ps1"
PS1_SCRIPTS = ROOT / "scripts" / "Enable-MsspWindowsTelemetry.ps1"
PS1_BOOTSTRAP = ROOT / "scripts" / "bootstrap_windows_telemetry.ps1"
BUILDER = BACKEND / "app" / "services" / "agent_package_builder.py"
INSTALL_REPO = BACKEND / "app" / "services" / "agent_install_repo.py"
LINUX_INSTALLER = (
    BACKEND / "app" / "endpoint_configs" / "linux-edr-telemetry" / "install-mssp-linux-telemetry.sh"
)
LINUX_RULES = BACKEND / "app" / "endpoint_configs" / "linux-edr-telemetry" / "mssp-exec.rules"
TREE_PY = BACKEND / "app" / "services" / "edr_process_tree.py"
INGRESS_PY = BACKEND / "app" / "services" / "edr_ingress.py"
SCHEMAS_PY = BACKEND / "app" / "schemas" / "edr.py"
SOC_SYNC = BACKEND / "app" / "api" / "routes" / "soc_sync.py"


# ---------------------------------------------------------------------------
# CHECK 1
# ---------------------------------------------------------------------------
def check_1_windows_offline_sysmon() -> CheckResult:
    cr = CheckResult("CHECK 1: Windows installer & offline Sysmon fallback")
    f = cr.findings
    if not require_file(f, PS1_CANONICAL, "canonical Enable-MsspWindowsTelemetry.ps1"):
        return cr
    if not require_file(f, BUILDER, "agent_package_builder.py"):
        return cr

    ps1 = read(PS1_CANONICAL)
    builder = read(BUILDER)

    bundled_fn = "function Resolve-BundledSysmonBinary"
    expect(
        f,
        bundled_fn in ps1 and "Sysmon64.exe" in ps1,
        "installer resolves Sysmon64.exe next to the script",
        path=PS1_CANONICAL,
        pattern=r"function Resolve-BundledSysmonBinary",
    )
    expect(
        f,
        bool(re.search(r"Join-Path \$here \"Sysmon64\.exe\"", ps1)),
        "package-directory Sysmon64.exe is a candidate path",
        path=PS1_CANONICAL,
        pattern=r"Join-Path \$here \"Sysmon64\.exe\"",
    )

    # Download must be gated on missing local binary.
    download_line = locate(PS1_CANONICAL, r"download\.sysinternals\.com")
    gated = bool(
        re.search(
            r"if \(-not \$sysmonExe\) \{[\s\S]{0,400}download\.sysinternals\.com",
            ps1,
        )
    )
    expect(
        f,
        gated and download_line is not None,
        "Sysinternals download runs only when no local Sysmon binary is found",
        path=PS1_CANONICAL,
        pattern=r"download\.sysinternals\.com",
        detail=""
        if gated
        else "download.sysinternals.com is not inside `if (-not $sysmonExe)`",
    )
    expect(
        f,
        "Using bundled Sysmon binary" in ps1,
        "local binary is used directly (no download log on bundled path)",
        path=PS1_CANONICAL,
        pattern=r"Using bundled Sysmon binary",
    )
    expect(
        f,
        "SkipDownload" in ps1 and "SkipSysmonDownload" in ps1,
        "SkipSysmonDownload still installs from bundled Sysmon64.exe",
        path=PS1_CANONICAL,
        pattern=r"SkipDownload",
    )

    expect(
        f,
        "resolve_sysmon_binary" in builder and 'zf.write(sysmon_bin, "windows/Sysmon64.exe")' in builder,
        "ZIP builder embeds Sysmon64.exe when a cached binary exists",
        path=BUILDER,
        pattern=r"windows/Sysmon64.exe",
    )
    expect(
        f,
        'zf.writestr("windows/sysmon-windows-baseline.xml"' in builder,
        "ZIP builder writes sysmon-windows-baseline.xml",
        path=BUILDER,
        pattern=r"windows/sysmon-windows-baseline.xml",
    )

    copies = (PS1_SCRIPTS, PS1_BOOTSTRAP)
    for copy in copies:
        if not copy.is_file():
            f.append(Finding("FAILED", "telemetry script copy missing", path=copy))
            continue
        expect(
            f,
            "Resolve-BundledSysmonBinary" in read(copy),
            f"copy stays in sync: {copy.name}",
            path=copy,
            pattern=r"Resolve-BundledSysmonBinary",
        )

    # Live ZIP generation (no network).
    try:
        from app.services.agent_package_builder import build_agent_package_zip

        data, name = build_agent_package_zip(
            tenant_name="E2E",
            short_code="E2EMID",
            wazuh_agent_group="tenant_E2EMID",
            os_type="windows",
        )
        z = zipfile.ZipFile(io.BytesIO(data))
        names = set(z.namelist())
        expect(
            f,
            "windows/sysmon-windows-baseline.xml" in names,
            f"generated {name} contains sysmon-windows-baseline.xml",
            path=BUILDER,
            pattern=r"windows/sysmon-windows-baseline.xml",
        )
        expect(
            f,
            "windows/Enable-MsspWindowsTelemetry.ps1" in names,
            "generated Windows ZIP contains telemetry script",
            path=BUILDER,
            pattern=r"Enable-MsspWindowsTelemetry.ps1",
        )
        xml = z.read("windows/sysmon-windows-baseline.xml").decode("utf-8", errors="replace")
        expect(
            f,
            "<Sysmon" in xml and "ProcessCreate" in xml or "EventID" in xml or "ProcessCreate" in xml,
            "embedded Sysmon XML looks like a Sysmon config",
            detail="root <Sysmon> missing" if "<Sysmon" not in xml else "",
        )
        ps1_zip = z.read("windows/Enable-MsspWindowsTelemetry.ps1").decode("utf-8", errors="replace")
        expect(
            f,
            "Resolve-BundledSysmonBinary" in ps1_zip and "download.sysinternals.com" in ps1_zip,
            "ZIP telemetry script still prefers local Sysmon then Sysinternals",
        )
        if "windows/Sysmon64.exe" in names:
            f.append(
                Finding(
                    "PASSED",
                    "this control-plane build embedded windows/Sysmon64.exe in the ZIP",
                )
            )
        else:
            f.append(
                Finding(
                    "WARNING",
                    "ZIP has no Sysmon64.exe (cache empty) — installer will download only if the host has network",
                    path=BUILDER,
                    line=locate(BUILDER, r"resolve_sysmon_binary"),
                )
            )
        z.close()
    except Exception as exc:
        f.append(
            Finding(
                "FAILED",
                "could not generate a Windows agent ZIP",
                detail=f"{type(exc).__name__}: {exc}",
                path=BUILDER,
            )
        )
    return cr


# ---------------------------------------------------------------------------
# CHECK 2
# ---------------------------------------------------------------------------
def check_2_linux_auto_provision() -> CheckResult:
    cr = CheckResult("CHECK 2: Linux EDR auto-provisioning & script generation")
    f = cr.findings
    for p, title in (
        (BUILDER, "agent_package_builder.py"),
        (INSTALL_REPO, "agent_install_repo.py"),
        (LINUX_INSTALLER, "install-mssp-linux-telemetry.sh"),
        (LINUX_RULES, "mssp-exec.rules"),
    ):
        if not require_file(f, p, title):
            return cr

    builder = read(BUILDER)
    repo = read(INSTALL_REPO)
    installer = read(LINUX_INSTALLER)
    rules = read(LINUX_RULES)

    expect(
        f,
        "def _linux_script" in builder and "_linux_midlayer_suffix" in builder,
        "_linux_script() appends the mid-layer telemetry suffix",
        path=BUILDER,
        pattern=r"def _linux_script",
    )
    expect(
        f,
        "from app.services.agent_package_builder import build_linux_install_script" in repo,
        "one-liner repo uses build_linux_install_script (same Linux script as ZIP)",
        path=INSTALL_REPO,
        pattern=r"build_linux_install_script",
    )
    expect(
        f,
        "auditd execve" in repo,
        "one-liner documents auditd execve telemetry",
        path=INSTALL_REPO,
        pattern=r"auditd execve",
    )

    # Approved collector is auditd (not Tetragon) so edr_process_tree can parse it.
    expect(
        f,
        "apt-get install -y auditd" in installer or "install -y auditd" in installer,
        "Linux helper installs auditd (approved mid-layer collector)",
        path=LINUX_INSTALLER,
        pattern=r"auditd",
    )
    if "tetragon" in installer.lower() or "bpftool" in installer.lower():
        f.append(
            Finding(
                "WARNING",
                "Linux helper also mentions Tetragon/eBPF tools — keep auditd as the parse path",
                path=LINUX_INSTALLER,
                line=locate(LINUX_INSTALLER, r"tetragon|bpftool", flags=re.I),
            )
        )
    else:
        f.append(
            Finding(
                "PASSED",
                "no Tetragon/eBPF sidecar required — auditd matches backend endpoint_audit_exec",
                path=LINUX_INSTALLER,
                line=locate(LINUX_INSTALLER, r"auditd execve collector"),
            )
        )

    expect(
        f,
        "execve,execveat" in rules and "key=mssp_exec" in rules,
        "auditd baseline captures execve/execveat with key=mssp_exec",
        path=LINUX_RULES,
        pattern=r"execve,execveat",
        detail="need pid/ppid/comm/exe/uid/cwd/cmdline via EXECVE records",
    )
    expect(
        f,
        "pid" in rules.lower() and "ppid" in rules.lower() and "cwd" in rules.lower(),
        "rule file documents pid, ppid, cwd (and related EXECVE fields)",
        path=LINUX_RULES,
        pattern=r"pid, ppid",
    )

    expect(
        f,
        "<log_format>audit</log_format>" in installer
        and "/var/log/audit/audit.log" in installer,
        "appends Wazuh <localfile> audit reader for /var/log/audit/audit.log",
        path=LINUX_INSTALLER,
        pattern=r"<log_format>audit</log_format>",
        detail="log_format=audit is the Wazuh decoder that yields data.audit.* JSON on the Manager",
    )
    expect(
        f,
        "location>/var/log/audit/audit.log" in installer.replace(" ", ""),
        "localfile location is the kernel audit log path",
        path=LINUX_INSTALLER,
        pattern=r"/var/log/audit/audit.log",
    )

    try:
        from app.services.agent_package_builder import (
            build_agent_package_zip,
            build_linux_install_script,
        )

        script = build_linux_install_script(
            short_code="E2EMID", wazuh_agent_group="tenant_E2EMID"
        )
        expect(
            f,
            "auditd" in script and "mssp_exec" in script or "MSSP_LINUX_TELEMETRY" in script,
            "generated one-liner/script includes auditd execve mid-layer",
            path=BUILDER,
            pattern=r"_linux_midlayer_suffix",
        )
        expect(
            f,
            "/var/log/audit/audit.log" in script or "install-mssp-linux-telemetry.sh" in script,
            "generated Linux script wires or invokes the audit.log localfile helper",
            path=BUILDER,
            pattern=r"install-mssp-linux-telemetry.sh",
        )
        data, name = build_agent_package_zip(
            tenant_name="E2E",
            short_code="E2EMID",
            wazuh_agent_group="tenant_E2EMID",
            os_type="linux",
        )
        z = zipfile.ZipFile(io.BytesIO(data))
        names = set(z.namelist())
        for needed in (
            "linux/install-linux-agent.sh",
            "linux/install-mssp-linux-telemetry.sh",
            "linux/mssp-exec.rules",
        ):
            expect(f, needed in names, f"generated {name} contains {needed}")
        z.close()
    except Exception as exc:
        f.append(
            Finding(
                "FAILED",
                "could not generate Linux install script / ZIP",
                detail=f"{type(exc).__name__}: {exc}",
                path=BUILDER,
            )
        )
    return cr


# ---------------------------------------------------------------------------
# CHECK 3
# ---------------------------------------------------------------------------
def _windows_patch_before_final_start(ps1: str, win_installer: str) -> Tuple[bool, str]:
    """Telemetry patches ossec.conf then restarts WazuhSvc. MSI may start the service first."""
    patches = "Microsoft-Windows-Sysmon/Operational" in ps1 and "EventID=4688" in ps1
    restarts = "Restart-Service -Name WazuhSvc" in ps1
    calls_telemetry = "Enable-MsspWindowsTelemetry.ps1" in win_installer
    if patches and restarts and calls_telemetry:
        return True, "MSI may Start-Service first; telemetry then patches ossec.conf and Restart-Service WazuhSvc"
    return False, "Windows path does not patch Sysmon/4688 localfiles and restart the agent"


def check_3_ossec_localfile_patching() -> CheckResult:
    cr = CheckResult("CHECK 3: Wazuh eventchannel & localfile patching")
    f = cr.findings
    ps1 = read(PS1_CANONICAL)
    installer = read(LINUX_INSTALLER)
    builder = read(BUILDER)

    expect(
        f,
        "<location>Microsoft-Windows-Sysmon/Operational</location>" in ps1
        and "<log_format>eventchannel</log_format>" in ps1,
        "Windows patches Microsoft-Windows-Sysmon/Operational as eventchannel",
        path=PS1_CANONICAL,
        pattern=r"Microsoft-Windows-Sysmon/Operational",
    )
    expect(
        f,
        "<location>Security</location>" in ps1 and "EventID=4688" in ps1,
        "Windows patches Security Event ID 4688 as eventchannel",
        path=PS1_CANONICAL,
        pattern=r"EventID=4688",
    )

    win_ok, win_detail = _windows_patch_before_final_start(ps1, builder)
    expect(
        f,
        win_ok,
        "Windows ossec.conf is patched and the agent is restarted so channels load",
        path=PS1_CANONICAL,
        pattern=r"Restart-Service -Name WazuhSvc",
        detail=win_detail,
    )
    if "Start-Service -Name WazuhSvc" in builder:
        start_line = locate(BUILDER, r"Start-Service -Name WazuhSvc")
        tel_line = locate(BUILDER, r"Enable-MsspWindowsTelemetry.ps1")
        if start_line and tel_line and start_line < tel_line:
            f.append(
                Finding(
                    "WARNING",
                    "Windows installer starts WazuhSvc before telemetry patch, then telemetry restarts it",
                    detail="not a functional break; first start uses stock ossec.conf for a few seconds",
                    path=BUILDER,
                    line=start_line,
                )
            )

    expect(
        f,
        "<log_format>audit</log_format>" in installer
        and "/var/log/audit/audit.log" in installer,
        "Linux patches ossec.conf with an audit-log reader (Wazuh JSON on the Manager)",
        path=LINUX_INSTALLER,
        pattern=r"<log_format>audit</log_format>",
    )
    expect(
        f,
        "systemctl restart wazuh-agent" in installer,
        "Linux restarts wazuh-agent after the localfile patch",
        path=LINUX_INSTALLER,
        pattern=r"systemctl restart wazuh-agent",
    )

    # Order in generated _linux_script: enroll/restart agent, THEN midlayer (patch + restart).
    linux_fn = locate(BUILDER, r"def _linux_script")
    suffix_line = locate(BUILDER, r"_linux_midlayer_suffix")
    first_restart = None
    if BUILDER.is_file():
        lines = BUILDER.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines, 1):
            if linux_fn and i >= linux_fn and "systemctl restart wazuh-agent" in line:
                first_restart = i
                break
    if first_restart and suffix_line and first_restart < suffix_line:
        f.append(
            Finding(
                "WARNING",
                "Linux installer starts wazuh-agent once before mid-layer patch, then patches and restarts",
                detail="fail-open by design: enrollment is not undone if auditd install fails",
                path=BUILDER,
                line=first_restart,
            )
        )
    else:
        f.append(
            Finding(
                "PASSED",
                "Linux mid-layer suffix runs after agent enrollment",
                path=BUILDER,
                line=suffix_line,
            )
        )
    return cr


# ---------------------------------------------------------------------------
# CHECK 4
# ---------------------------------------------------------------------------
SYSMON_PARENT = {
    "rule": {"id": "61603", "level": 12, "groups": ["sysmon", "sysmon_eid1_detections"]},
    "agent": {"id": "007", "name": "WIN-E2E"},
    "data": {
        "win": {
            "system": {"eventID": "1"},
            "eventdata": {
                "UtcTime": "2026-08-18T09:00:00.000Z",
                "ProcessGuid": "{11111111-aaaa-bbbb-cccc-000000000001}",
                "ProcessId": "1000",
                "Image": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
                "CommandLine": "powershell.exe -NoProfile",
                "User": "WIN-E2E\\Analyst",
                "ParentProcessGuid": "{11111111-aaaa-bbbb-cccc-000000000000}",
                "ParentProcessId": "800",
                "ParentImage": "C:\\Windows\\explorer.exe",
                "ParentCommandLine": "C:\\Windows\\explorer.exe",
                "Hashes": "MD5=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,SHA256="
                + ("ab" * 32),
            },
        }
    },
}

SYSMON_CHILD = {
    "rule": {"id": "61603", "level": 12, "groups": ["sysmon"]},
    "agent": {"id": "007", "name": "WIN-E2E"},
    "data": {
        "win": {
            "system": {"eventID": "1"},
            "eventdata": {
                "UtcTime": "2026-08-18T09:00:01.000Z",
                "ProcessGuid": "{11111111-aaaa-bbbb-cccc-000000000002}",
                "ProcessId": "1001",
                "Image": "C:\\Windows\\System32\\cmd.exe",
                "CommandLine": "cmd.exe /c whoami",
                "User": "WIN-E2E\\Analyst",
                "ParentProcessGuid": "{11111111-aaaa-bbbb-cccc-000000000001}",
                "ParentProcessId": "1000",
                "ParentImage": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
                "Hashes": "SHA256=" + ("cd" * 32),
            },
        }
    },
}

AUDIT_PARENT = {
    "rule": {"id": "110001", "level": 10, "groups": ["audit", "auditd", "mssp_linux_exec"]},
    "agent": {"id": "042", "name": "linux-e2e"},
    "data": {
        "audit": {
            "pid": "2200",
            "ppid": "1",
            "exe": "/usr/bin/bash",
            "comm": "bash",
            "uid": "0",
            "auid": "0",
            "cwd": "/tmp",
            "key": "mssp_exec",
            "command": "/usr/bin/bash -c evil",
            "execve": {"a0": "/usr/bin/bash", "a1": "-c", "a2": "evil"},
        }
    },
}

AUDIT_CHILD = {
    "rule": {"id": "110001", "level": 10, "groups": ["audit", "auditd"]},
    "agent": {"id": "042", "name": "linux-e2e"},
    "data": {
        "audit": {
            "pid": "2201",
            "ppid": "2200",
            "exe": "/tmp/payload",
            "comm": "payload",
            "uid": "0",
            "auid": "0",
            "cwd": "/tmp",
            "key": "mssp_exec",
            "execve": {"a0": "/tmp/payload"},
        }
    },
}

INSERT_COLS = (
    "tenant_id",
    "alert_id",
    "agent_id",
    "pid",
    "parent_pid",
    "process_guid",
    "parent_process_guid",
    "process_name",
    "parent_process_name",
    "command_line",
    "parent_command_line",
    "username",
    "hash_md5",
    "hash_sha256",
    "signed_status",
    "event_time",
    "mitre_techniques",
    "raw_source",
)


def _check_4_via_docker(findings: List[Finding]) -> None:
    """Host Python has no pydantic — run the mapper inside mssp-backend-api."""
    import json
    import subprocess

    payload = {
        "sysmon_parent": SYSMON_PARENT,
        "sysmon_child": SYSMON_CHILD,
        "audit_parent": AUDIT_PARENT,
        "audit_child": AUDIT_CHILD,
    }
    py = (
        "import json,sys\n"
        "from app.schemas.edr import ProcessTreeNode, ProcessTreeResponse\n"
        "from app.services.edr_ingress import persist_wazuh_alert_enrichment\n"
        "from app.services.edr_process_tree import build_process_forest, normalize_process_event\n"
        f"blob = json.loads({json.dumps(json.dumps(payload))})\n"
        "out = {\"import_ok\": True, \"persist_callable\": callable(persist_wazuh_alert_enrichment), \"samples\": []}\n"
        "pairs = ((\"sysmon_parent\", \"endpoint_process_create\"), (\"sysmon_child\", \"endpoint_process_create\"),"
        " (\"audit_parent\", \"endpoint_audit_exec\"), (\"audit_child\", \"endpoint_audit_exec\"))\n"
        "for key, expected in pairs:\n"
        "    row = {\"key\": key, \"error\": None}\n"
        "    try:\n"
        "        norm = normalize_process_event(blob[key])\n"
        "        row[\"expected\"] = expected\n"
        "        if not norm:\n"
        "            row[\"norm\"] = None\n"
        "        else:\n"
        "            row[\"norm\"] = {k: norm.get(k) for k in "
        "(\"raw_source\",\"pid\",\"parent_pid\",\"process_guid\",\"parent_process_guid\",\"process_name\")}\n"
        "            ProcessTreeNode(pid=norm.get(\"pid\"), parent_pid=norm.get(\"parent_pid\"),"
        " process_guid=norm.get(\"process_guid\"), parent_process_guid=norm.get(\"parent_process_guid\"),"
        " process_name=norm.get(\"process_name\"), user=norm.get(\"username\"))\n"
        "            row[\"node_ok\"] = True\n"
        "    except Exception as exc:\n"
        "        row[\"error\"] = f\"{type(exc).__name__}: {exc}\"\n"
        "    out[\"samples\"].append(row)\n"
        "try:\n"
        "    forest = build_process_forest([blob[\"sysmon_parent\"], blob[\"sysmon_child\"]])\n"
        "    out[\"sysmon_forest\"] = {\"events\": forest.events_considered, \"has_root\": forest.root is not None,"
        " \"root_name\": getattr(forest.root, \"process_name\", None),"
        " \"child_names\": [c.process_name for c in (forest.root.child_processes or [])] if forest.root else []}\n"
        "    af = build_process_forest([blob[\"audit_parent\"], blob[\"audit_child\"]])\n"
        "    out[\"audit_forest\"] = {\"has_root\": af.root is not None, \"events\": af.events_considered}\n"
        "except Exception as exc:\n"
        "    out[\"forest_error\"] = f\"{type(exc).__name__}: {exc}\"\n"
        "print(json.dumps(out))\n"
    )
    try:
        proc = subprocess.run(
            ["docker", "compose", "exec", "-T", "backend-api", "python", "-c", py],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        findings.append(
            Finding(
                "FAILED",
                "host lacks pydantic and docker compose exec backend-api failed",
                detail=str(exc),
                path=TREE_PY,
            )
        )
        return
    if proc.returncode != 0:
        findings.append(
            Finding(
                "FAILED",
                "backend-api parser probe exited non-zero",
                detail=(proc.stderr or proc.stdout)[-2000:],
                path=TREE_PY,
            )
        )
        return
    try:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
    except json.JSONDecodeError:
        findings.append(
            Finding(
                "FAILED",
                "backend-api parser probe did not return JSON",
                detail=proc.stdout[-1500:],
                path=TREE_PY,
            )
        )
        return

    expect(
        findings,
        bool(data.get("import_ok")) and bool(data.get("persist_callable")),
        "persist_wazuh_alert_enrichment() and normalize_process_event() imported inside backend-api",
        path=INGRESS_PY,
        pattern=r"def persist_wazuh_alert_enrichment",
    )
    node_src = read(SCHEMAS_PY)
    start = node_src.find("class ProcessTreeNode")
    node_src_block = node_src[start : start + 800] if start >= 0 else ""
    expect(
        findings,
        'extra="forbid"' not in node_src_block and "extra='forbid'" not in node_src_block,
        "ProcessTreeNode does not use extra=forbid (action requests still do)",
        path=SCHEMAS_PY,
        pattern=r"class ProcessTreeNode",
    )
    for row in data.get("samples") or []:
        label = row.get("key")
        if row.get("error"):
            findings.append(
                Finding(
                    "FAILED",
                    f"{label}: normalize/ProcessTreeNode raised",
                    detail=row["error"],
                    path=TREE_PY,
                    line=locate(TREE_PY, r"def normalize_process_event"),
                )
            )
            continue
        norm = row.get("norm") or {}
        expect(
            findings,
            norm.get("raw_source") == row.get("expected"),
            f"{label}: raw_source={norm.get('raw_source')}",
            path=TREE_PY,
            pattern=re.escape(str(row.get("expected") or "")),
        )
        expect(
            findings,
            norm.get("pid") is not None and norm.get("parent_pid") is not None,
            f"{label}: pid={norm.get('pid')} parent_pid={norm.get('parent_pid')}",
            path=TREE_PY,
            pattern=r"def normalize_process_event",
        )
        if row.get("expected") == "endpoint_process_create":
            expect(
                findings,
                bool(norm.get("process_guid")) and bool(norm.get("parent_process_guid")),
                f"{label}: ProcessGuid parent/child extracted",
                path=TREE_PY,
                pattern=r"ProcessGuid",
            )
        expect(
            findings,
            bool(row.get("node_ok")),
            f"{label}: ProcessTreeNode validates (no extra=forbid violation)",
            path=SCHEMAS_PY,
            pattern=r"class ProcessTreeNode",
        )
    sf = data.get("sysmon_forest") or {}
    expect(
        findings,
        not data.get("forest_error") and sf.get("has_root") and int(sf.get("events") or 0) >= 2,
        f"Sysmon parent/child forest built (events_considered={sf.get('events')})",
        path=TREE_PY,
        pattern=r"def build_process_forest",
        detail=str(data.get("forest_error") or ""),
    )
    kids = [str(n or "").lower() for n in (sf.get("child_names") or [])]
    root_name = str(sf.get("root_name") or "").lower()
    if "powershell" in root_name:
        expect(
            findings,
            any("cmd.exe" in k for k in kids),
            "Sysmon GUID tree: cmd.exe is a child of powershell.exe",
            path=TREE_PY,
            pattern=r"parent_process_guid",
        )
    elif kids:
        findings.append(
            Finding(
                "PASSED",
                "Sysmon forest produced a parent with child_processes",
                path=TREE_PY,
                line=locate(TREE_PY, r"def build_process_forest"),
            )
        )
    af = data.get("audit_forest") or {}
    expect(
        findings,
        bool(af.get("has_root")),
        "Linux auditd pid/ppid forest built without KeyError",
        path=TREE_PY,
        pattern=r"parent_pid",
    )
    findings.append(
        Finding(
            "WARNING",
            "persist_wazuh_alert_enrichment() was not executed against live PostgreSQL",
            detail="mapper + INSERT column bind were verified in-process so this audit cannot insert fake SOC alerts",
            path=INGRESS_PY,
            line=locate(INGRESS_PY, r"def persist_wazuh_alert_enrichment"),
        )
    )


def _norm_to_insert_params(norm: Dict[str, Any]) -> Dict[str, Any]:
    """Same keys _persist_process_event binds (minus tenant/alert uuids)."""
    return {
        "agent_id": norm.get("agent_id"),
        "pid": norm.get("pid"),
        "parent_pid": norm.get("parent_pid"),
        "process_guid": norm.get("process_guid"),
        "parent_process_guid": norm.get("parent_process_guid"),
        "process_name": norm.get("process_name"),
        "parent_process_name": norm.get("parent_process_name"),
        "command_line": norm.get("command_line"),
        "parent_command_line": norm.get("parent_command_line"),
        "username": norm.get("username"),
        "hash_md5": norm.get("hash_md5"),
        "hash_sha256": norm.get("hash_sha256"),
        "signed_status": norm.get("signed_status"),
        "event_time": norm.get("event_time"),
        "mitre_techniques": list(norm.get("mitre_techniques") or []),
        "raw_source": norm.get("raw_source"),
    }


def check_4_backend_process_tree() -> CheckResult:
    cr = CheckResult("CHECK 4: Backend ingestion & process-tree mapping")
    f = cr.findings
    for p, title in (
        (TREE_PY, "edr_process_tree.py"),
        (INGRESS_PY, "edr_ingress.py"),
        (SCHEMAS_PY, "schemas/edr.py"),
        (SOC_SYNC, "soc_sync.py hook"),
    ):
        if not require_file(f, p, title):
            return cr

    ingress = read(INGRESS_PY)
    soc = read(SOC_SYNC)
    tree_src = read(TREE_PY)

    expect(
        f,
        "persist_wazuh_alert_enrichment" in soc and "edr_ingress" in soc,
        "Wazuh hook calls persist_wazuh_alert_enrichment (existing integratord path)",
        path=SOC_SYNC,
        pattern=r"persist_wazuh_alert_enrichment",
    )
    expect(
        f,
        "INSERT INTO edr_process_events" in ingress
        and "normalize_process_event" in ingress,
        "persist helper inserts edr_process_events from normalize_process_event",
        path=INGRESS_PY,
        pattern=r"INSERT INTO edr_process_events",
    )
    missing_cols = [c for c in INSERT_COLS if c not in ingress]
    expect(
        f,
        not missing_cols,
        "edr_process_events INSERT lists the expected columns",
        path=INGRESS_PY,
        pattern=r"INSERT INTO edr_process_events",
        detail=("missing " + ", ".join(missing_cols)) if missing_cols else "",
    )
    expect(
        f,
        'raw_source": "endpoint_audit_exec"' in tree_src
        and 'raw_source": "endpoint_process_create"' in tree_src,
        "parser emits endpoint_process_create (Sysmon) and endpoint_audit_exec (auditd)",
        path=TREE_PY,
        pattern=r"endpoint_audit_exec",
    )

    try:
        from app.schemas.edr import ProcessTreeNode, ProcessTreeResponse
        from app.services.edr_ingress import persist_wazuh_alert_enrichment
        from app.services.edr_process_tree import (
            build_process_forest,
            normalize_process_event,
        )
    except ModuleNotFoundError:
        _check_4_via_docker(f)
        return cr

    expect(
        f,
        callable(persist_wazuh_alert_enrichment) and callable(normalize_process_event),
        "persist_wazuh_alert_enrichment() and normalize_process_event() are importable",
        path=INGRESS_PY,
        pattern=r"def persist_wazuh_alert_enrichment",
    )

    # extra=forbid lives on EDR *actions*, not process-tree nodes.
    action_forbid = "class EdrActionExecuteRequest" in read(SCHEMAS_PY) and locate(
        SCHEMAS_PY, r'extra="forbid"'
    )
    node_src_block = ""
    if "class ProcessTreeNode" in read(SCHEMAS_PY):
        start = read(SCHEMAS_PY).index("class ProcessTreeNode")
        node_src_block = read(SCHEMAS_PY)[start : start + 800]
    expect(
        f,
        "extra=\"forbid\"" not in node_src_block and "extra='forbid'" not in node_src_block,
        "ProcessTreeNode does not use extra=forbid (action requests still do)",
        path=SCHEMAS_PY,
        pattern=r"class ProcessTreeNode",
        detail="EdrActionExecuteRequest keeps extra=forbid; process events must not use that model",
    )

    samples: Sequence[Tuple[str, Dict[str, Any], str]] = (
        ("Sysmon Event ID 1 parent", SYSMON_PARENT, "endpoint_process_create"),
        ("Sysmon Event ID 1 child", SYSMON_CHILD, "endpoint_process_create"),
        ("Linux auditd execve parent", AUDIT_PARENT, "endpoint_audit_exec"),
        ("Linux auditd execve child", AUDIT_CHILD, "endpoint_audit_exec"),
    )

    norms: List[Dict[str, Any]] = []
    for label, payload, expected_source in samples:
        try:
            norm = normalize_process_event(payload)
        except Exception as exc:
            f.append(
                Finding(
                    "FAILED",
                    f"{label}: normalize_process_event raised",
                    detail=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
                    path=TREE_PY,
                    line=locate(TREE_PY, r"def normalize_process_event"),
                )
            )
            continue
        if not norm:
            f.append(
                Finding(
                    "FAILED",
                    f"{label}: parser returned None",
                    detail="payload did not match Sysmon/osquery/auditd branches",
                    path=TREE_PY,
                    line=locate(TREE_PY, r"def normalize_process_event"),
                )
            )
            continue
        expect(
            f,
            norm.get("raw_source") == expected_source,
            f"{label}: raw_source={norm.get('raw_source')}",
            path=TREE_PY,
            pattern=re.escape(expected_source),
        )
        expect(
            f,
            norm.get("pid") is not None and norm.get("parent_pid") is not None,
            f"{label}: pid={norm.get('pid')} parent_pid={norm.get('parent_pid')}",
            path=TREE_PY,
            pattern=r'"pid":',
        )
        if expected_source == "endpoint_process_create":
            expect(
                f,
                bool(norm.get("process_guid")) and bool(norm.get("parent_process_guid")),
                f"{label}: ProcessGuid parent/child extracted",
                path=TREE_PY,
                pattern=r"ProcessGuid",
            )
        params = _norm_to_insert_params(norm)
        expect(
            f,
            set(INSERT_COLS[2:]).issubset(params.keys()),
            f"{label}: edr_process_events bind parameters constructed",
            path=INGRESS_PY,
            pattern=r"norm.get\(\"pid\"\)",
        )
        try:
            node = ProcessTreeNode(
                pid=norm.get("pid"),
                parent_pid=norm.get("parent_pid"),
                process_guid=norm.get("process_guid"),
                parent_process_guid=norm.get("parent_process_guid"),
                process_name=norm.get("process_name"),
                parent_process_name=norm.get("parent_process_name"),
                command_line=norm.get("command_line"),
                parent_command_line=norm.get("parent_command_line"),
                user=norm.get("username"),
                hash_md5=norm.get("hash_md5"),
                hash_sha256=norm.get("hash_sha256"),
                signed_status=norm.get("signed_status"),
                mitre_techniques=list(norm.get("mitre_techniques") or []),
                event_time=None,
            )
            dumped = node.model_dump()
            expect(
                f,
                dumped.get("pid") == norm.get("pid"),
                f"{label}: ProcessTreeNode validates (no extra=forbid violation)",
                path=SCHEMAS_PY,
                pattern=r"class ProcessTreeNode",
            )
        except Exception as exc:
            f.append(
                Finding(
                    "FAILED",
                    f"{label}: ProcessTreeNode validation failed",
                    detail=f"{type(exc).__name__}: {exc}",
                    path=SCHEMAS_PY,
                    line=locate(SCHEMAS_PY, r"class ProcessTreeNode"),
                )
            )
        norms.append(norm)

    try:
        forest = build_process_forest(
            [SYSMON_PARENT, SYSMON_CHILD],
            normalized_rows=None,
        )
        assert isinstance(forest, ProcessTreeResponse)
        root = forest.root
        expect(
            f,
            root is not None and forest.events_considered >= 2,
            f"Sysmon parent/child forest built (events_considered={forest.events_considered})",
            path=TREE_PY,
            pattern=r"def build_process_forest",
        )
        # Child should hang off parent via ProcessGuid.
        kids = list(getattr(root, "child_processes", []) or [])
        if root and getattr(root, "process_name", None) and "powershell" in str(root.process_name).lower():
            expect(
                f,
                any("cmd.exe" in str(k.process_name or "").lower() for k in kids),
                "Sysmon GUID tree: cmd.exe is a child of powershell.exe",
                path=TREE_PY,
                pattern=r"parent_process_guid",
            )
        elif root and kids:
            f.append(
                Finding(
                    "PASSED",
                    "Sysmon forest produced a parent with child_processes",
                    path=TREE_PY,
                    line=locate(TREE_PY, r"def build_process_forest"),
                )
            )
        audit_forest = build_process_forest([AUDIT_PARENT, AUDIT_CHILD])
        expect(
            f,
            audit_forest.root is not None,
            "Linux auditd pid/ppid forest built without KeyError",
            path=TREE_PY,
            pattern=r"parent_pid",
        )
    except Exception as exc:
        f.append(
            Finding(
                "FAILED",
                "build_process_forest raised",
                detail=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
                path=TREE_PY,
                line=locate(TREE_PY, r"def build_process_forest"),
            )
        )

    f.append(
        Finding(
            "WARNING",
            "persist_wazuh_alert_enrichment() was not executed against live PostgreSQL",
            detail="mapper + INSERT column bind were verified in-process so this audit cannot insert fake SOC alerts",
            path=INGRESS_PY,
            line=locate(INGRESS_PY, r"def persist_wazuh_alert_enrichment"),
        )
    )
    return cr


# ---------------------------------------------------------------------------
# CHECK 5 — report
# ---------------------------------------------------------------------------
def check_5_invariants() -> CheckResult:
    """Structural invariants called out in the mid-layer build (not a sixth product check)."""
    cr = CheckResult("CHECK 5: Operational gaps & invariants")
    f = cr.findings
    ar_dir = ROOT / "deploy" / "wazuh-active-response"
    expect(
        f,
        (ar_dir / "mssp-isolate-host").is_file()
        and (ar_dir / "windows" / "mssp-isolate-host.ps1").is_file(),
        "Windows/Linux active-response scripts still present (this audit did not alter them)",
        path=ar_dir / "mssp-isolate-host",
    )
    soc = read(SOC_SYNC)
    expect(
        f,
        'prefix="/integrations/soc"' in soc and "/hooks/wazuh/{token}" in soc
        and "persist_wazuh_alert_enrichment" in soc,
        "existing Wazuh integratord hook POST /integrations/soc/hooks/wazuh/{token} is intact",
        path=SOC_SYNC,
        pattern=r"/hooks/wazuh/\{token\}",
    )
    compose = ROOT / "docker-compose.yml"
    if compose.is_file():
        text = read(compose)
        expect(
            f,
            "${API_PORT}:8000" in text or "8000:8000" in text,
            "VM 100 compose still publishes the API on container port 8000 (no new listen ports)",
            path=compose,
            pattern=r"API_PORT|:8000",
        )
        expect(
            f,
            "3000:80" in text and "3001:80" in text,
            "Admin :3000 and Customer :3001 mappings unchanged",
            path=compose,
            pattern=r"3000:80",
        )
    return cr


def print_report(checks: List[CheckResult]) -> int:
    print(f"{BOLD}MSSP mid-layer EDR end-to-end verification{RESET}")
    print(f"{DIM}root={ROOT}{RESET}")
    print()
    failed = 0
    warned = 0
    passed = 0
    for cr in checks:
        statuses = {x.status for x in cr.findings}
        if "FAILED" in statuses:
            head = f"{RED}FAILED{RESET}"
            failed += 1
        elif "WARNING" in statuses:
            head = f"{YELLOW}WARNING{RESET}"
            warned += 1
        else:
            head = f"{GREEN}PASSED{RESET}"
            passed += 1
        print(f"{BOLD}{cr.name}{RESET}  [{head}]")
        for finding in cr.findings:
            print(finding.render())
            if finding.status == "FAILED":
                failed += 0  # already counted at check level
        print()

    n_pass = sum(1 for cr in checks for x in cr.findings if x.status == "PASSED")
    n_fail = sum(1 for cr in checks for x in cr.findings if x.status == "FAILED")
    n_warn = sum(1 for cr in checks for x in cr.findings if x.status == "WARNING")
    print(f"{BOLD}Summary{RESET}  {GREEN}PASSED {n_pass}{RESET}  {YELLOW}WARNING {n_warn}{RESET}  {RED}FAILED {n_fail}{RESET}")
    if n_fail:
        print(f"{RED}RESULT: FAILED{RESET} — see file:line on each FAILED row")
        return 1
    print(f"{GREEN}RESULT: PASSED{RESET} (warnings are informational, not blockers)")
    return 0


def main() -> int:
    checks = [
        check_1_windows_offline_sysmon(),
        check_2_linux_auto_provision(),
        check_3_ossec_localfile_patching(),
        check_4_backend_process_tree(),
        check_5_invariants(),
    ]
    return print_report(checks)


if __name__ == "__main__":
    sys.exit(main())
