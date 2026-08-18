#!/usr/bin/env python3
"""Master automated verifier for the MSSP control-plane + engine architecture.

CRITICAL RULE: Whenever a change is made to platform architecture, API schemas,
engine rules, or agent installers, this script MUST be updated to include
programmatic test assertions for the new capability, and executed to confirm
0 failures before declaring work complete.

Standalone. Does not write to PostgreSQL, mutate running engines, or open ports.
Exit 0 when there are no FAILED checks. With --release, GAP findings also fail
the process (required for production/cloud cutover). Day-to-day runs without
--release still exit 0 when only WARNINGs remain.

Usage:
  python3 scripts/verify_platform_state.py
  python3 scripts/verify_platform_state.py --release   # GAP counts as failure
"""

from __future__ import annotations

import argparse
import ast
import io
import os
import re
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend-api"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("MSSP_SKIP_SYSMON_CACHE_DOWNLOAD", "1")

if sys.stdout.isatty() and os.getenv("NO_COLOR", "") == "":
    GREEN, YELLOW, RED, MAGENTA, BOLD, DIM, RESET = (
        "\033[32m",
        "\033[33m",
        "\033[31m",
        "\033[35m",
        "\033[1m",
        "\033[2m",
        "\033[0m",
    )
else:
    GREEN = YELLOW = RED = MAGENTA = BOLD = DIM = RESET = ""

# MSSP-owned Wazuh rule IDs (do not collide with upstream 92057 / 92213 / 100049).
MSSP_RULE_ID_MIN = 110000
MSSP_RULE_ID_MAX = 119999
FORBIDDEN_RULE_IDS = {92057, 92213, 100049}

REQUIRED_SOURCE_TOOLS = (
    "wazuh",
    "suricata",
    "zeek",
    "misp",
    "velociraptor",
    "endpoint_kernel",
    "nuclei",
    "vuls",
    "greenbone",
)

ENGINE_CATALOG = (
    {
        "name": "wazuh",
        "playbook": ROOT / "ansible" / "playbooks" / "wazuh-stack-install.yml",
        "adapters": (
            ROOT / "backend-api" / "app" / "api" / "routes" / "soc_sync.py",
            ROOT / "backend-api" / "app" / "services" / "soc_sync_service.py",
        ),
        "persist": "INSERT INTO security_alerts",
        "source_tool": "wazuh",
        "live_required": True,
    },
    {
        "name": "suricata",
        "playbook": ROOT / "ansible" / "playbooks" / "suricata-sensor.yml",
        "adapters": (
            ROOT / "backend-api" / "app" / "services" / "ndr_service.py",
            ROOT / "backend-api" / "app" / "api" / "routes" / "ndr.py",
        ),
        "persist": "INSERT INTO tenant_ndr_events",
        "source_tool": "suricata",
        "live_required": True,
    },
    {
        "name": "zeek",
        "playbook": ROOT / "ansible" / "playbooks" / "zeek.yml",
        "adapters": (
            ROOT / "backend-api" / "app" / "services" / "ndr_service.py",
            ROOT / "backend-api" / "app" / "api" / "routes" / "ndr.py",
        ),
        "persist": "INSERT INTO tenant_ndr_events",
        "source_tool": "zeek",
        "live_required": True,
    },
    {
        "name": "misp",
        "playbook": ROOT / "ansible" / "playbooks" / "misp.yml",
        "adapters": (
            ROOT / "backend-api" / "app" / "services" / "misp_client.py",
            ROOT / "backend-api" / "app" / "services" / "threat_intel_service.py",
            ROOT / "backend-api" / "app" / "api" / "routes" / "threat_intel.py",
        ),
        "persist": "INSERT INTO tenant_threat_intel_iocs",
        "source_tool": "misp",
        "live_required": True,
    },
    {
        "name": "velociraptor",
        "playbook": ROOT / "ansible" / "playbooks" / "velociraptor.yml",
        "adapters": (
            ROOT / "backend-api" / "app" / "services" / "velociraptor_client.py",
            ROOT / "backend-api" / "app" / "services" / "endpoint_forensics_service.py",
            ROOT / "backend-api" / "app" / "api" / "routes" / "endpoint_forensics.py",
        ),
        "persist": "INSERT INTO tenant_forensics_collections",
        "source_tool": "velociraptor",
        "live_required": True,
    },
)

REQUIRED_ROUTES = (
    ("/health", "GET"),
    ("/integrations/soc/hooks/wazuh/{token}", "POST"),
    ("/customer/ndr/{short_code}/summary", "GET"),
    ("/admin/ndr/{tenant_ref}/sync", "POST"),
    ("/customer/threat-intel/{short_code}/summary", "GET"),
    ("/admin/threat-intel/{tenant_ref}/sync", "POST"),
    ("/customer/forensics/{short_code}/summary", "GET"),
    ("/v1/edr/actions/execute", "POST"),
)


@dataclass
class Finding:
    status: str  # PASSED | FAILED | WARNING | GAP
    title: str
    detail: str = ""
    path: Optional[Path] = None
    line: Optional[int] = None

    def render(self) -> str:
        color = {
            "PASSED": GREEN,
            "FAILED": RED,
            "WARNING": YELLOW,
            "GAP": MAGENTA,
        }.get(self.status, "")
        loc = ""
        if self.path is not None:
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

    @property
    def gaps(self) -> int:
        return sum(1 for f in self.findings if f.status == "GAP")


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
    findings.append(Finding("FAILED", title, detail="file does not exist", path=path))
    return False


def expect(
    findings: List[Finding],
    ok: bool,
    title: str,
    *,
    path: Optional[Path] = None,
    pattern: Optional[str] = None,
    detail: str = "",
    status_if_false: str = "FAILED",
) -> None:
    line = locate(path, pattern) if path is not None and pattern else None
    if ok:
        findings.append(Finding("PASSED", title, detail=detail, path=path, line=line))
        return
    findings.append(
        Finding(
            status_if_false,
            title,
            detail=detail or (f"pattern not found: {pattern}" if pattern else "condition was false"),
            path=path,
            line=line,
        )
    )


def docker_backend_python(code: str, timeout: int = 60) -> Tuple[int, str, str]:
    proc = subprocess.run(
        ["docker", "compose", "exec", "-T", "backend-api", "python", "-c", code],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


# ---------------------------------------------------------------------------
# CHECK 1 — Wazuh & EDR pipeline
# ---------------------------------------------------------------------------
SYSMON_EVENT = {
    "rule": {"id": "61603", "level": 12, "groups": ["sysmon"]},
    "agent": {"id": "007", "name": "WIN-QA"},
    "data": {
        "win": {
            "system": {"eventID": "1"},
            "eventdata": {
                "ProcessId": "1000",
                "ParentProcessId": "800",
                "Image": "C:\\\\Windows\\\\System32\\\\cmd.exe",
                "ParentImage": "C:\\\\Windows\\\\explorer.exe",
                "CommandLine": "cmd.exe",
                "User": "WIN-QA\\\\User",
                "ProcessGuid": "{11111111-aaaa-bbbb-cccc-000000000001}",
                "ParentProcessGuid": "{11111111-aaaa-bbbb-cccc-000000000000}",
            },
        }
    },
}

AUDIT_EVENT = {
    "rule": {"id": "110001", "level": 10, "groups": ["audit", "auditd"]},
    "agent": {"id": "042", "name": "linux-qa"},
    "data": {
        "audit": {
            "pid": "2200",
            "ppid": "1",
            "exe": "/usr/bin/bash",
            "comm": "bash",
            "uid": "0",
            "key": "mssp_exec",
            "execve": {"a0": "/usr/bin/bash", "a1": "-c", "a2": "id"},
        }
    },
}


def check_edr_pipeline() -> CheckResult:
    cr = CheckResult("CHECK 1: Wazuh & EDR pipeline")
    f = cr.findings
    tree = BACKEND / "app" / "services" / "edr_process_tree.py"
    ingress = BACKEND / "app" / "services" / "edr_ingress.py"
    schemas = BACKEND / "app" / "schemas" / "edr.py"
    builder = BACKEND / "app" / "services" / "agent_package_builder.py"
    soc = BACKEND / "app" / "api" / "routes" / "soc_sync.py"
    ps1 = BACKEND / "app" / "endpoint_configs" / "Enable-MsspWindowsTelemetry.ps1"
    linux_sh = BACKEND / "app" / "endpoint_configs" / "linux-edr-telemetry" / "install-mssp-linux-telemetry.sh"

    for p, title in (
        (tree, "edr_process_tree.py"),
        (ingress, "edr_ingress.py"),
        (schemas, "schemas/edr.py"),
        (builder, "agent_package_builder.py"),
        (soc, "soc_sync Wazuh hook"),
        (ps1, "Windows telemetry installer"),
        (linux_sh, "Linux auditd telemetry installer"),
    ):
        if not require_file(f, p, title):
            return cr

    sch = read(schemas)
    expect(
        f,
        'class ProcessTreeNode' in sch and 'extra="forbid"' not in sch.split("class ProcessTreeNode", 1)[-1].split("class ", 1)[0],
        "ProcessTreeNode does not use extra=forbid (Sysmon/auditd extra fields must not 422)",
        path=schemas,
        pattern=r"class ProcessTreeNode",
    )
    expect(
        f,
        'class EdrActionExecuteRequest' in sch and 'extra="forbid"' in sch.split("class EdrActionExecuteRequest", 1)[-1].split("class ", 1)[0],
        "EdrActionExecuteRequest keeps extra=forbid",
        path=schemas,
        pattern=r'extra="forbid"',
    )
    expect(
        f,
        "endpoint_process_create" in read(tree) and "endpoint_audit_exec" in read(tree),
        "parser emits endpoint_process_create (Sysmon) and endpoint_audit_exec (auditd)",
        path=tree,
        pattern=r"endpoint_audit_exec",
    )
    expect(
        f,
        "persist_wazuh_alert_enrichment" in read(ingress) and "persist_wazuh_alert_enrichment" in read(soc),
        "Wazuh hook persists process-tree enrichment (existing integratord path)",
        path=soc,
        pattern=r"persist_wazuh_alert_enrichment",
    )
    expect(
        f,
        "Microsoft-Windows-Sysmon/Operational" in read(ps1) and "4688" in read(ps1),
        "Windows ossec.conf wires Sysmon eventchannel + Security 4688",
        path=ps1,
        pattern=r"Microsoft-Windows-Sysmon/Operational",
    )
    expect(
        f,
        "<log_format>audit</log_format>" in read(linux_sh) and "/var/log/audit/audit.log" in read(linux_sh),
        "Linux ossec.conf wires audit.log localfile (log_format=audit)",
        path=linux_sh,
        pattern=r"log_format>audit",
    )

    # Live process-tree mapping (pydantic lives in the API image).
    mapper_py = (
        "from app.schemas.edr import ProcessTreeNode, EdrActionExecuteRequest\n"
        "from app.services.edr_process_tree import normalize_process_event, _node_from_normalized\n"
        "from pydantic import ValidationError\n"
        "import json\n"
        f"sysmon={SYSMON_EVENT!r}\n"
        f"audit={AUDIT_EVENT!r}\n"
        "errors=[]\n"
        "for label, blob, expect_src in ("
        "('sysmon', sysmon, 'endpoint_process_create'),"
        "('auditd', audit, 'endpoint_audit_exec')):\n"
        "    n = normalize_process_event(blob)\n"
        "    if not n:\n"
        "        errors.append(label+': normalize returned None')\n"
        "        continue\n"
        "    if n.get('raw_source') != expect_src:\n"
        "        errors.append(label+': raw_source='+str(n.get('raw_source')))\n"
        "        continue\n"
        "    try:\n"
        "        node = _node_from_normalized(n)\n"
        "        ProcessTreeNode.model_validate(node.model_dump())\n"
        "    except ValidationError as exc:\n"
        "        errors.append(label+': '+str(exc))\n"
        "cfg = getattr(EdrActionExecuteRequest, 'model_config', {}) or {}\n"
        "extra = cfg.get('extra') if isinstance(cfg, dict) else getattr(cfg, 'extra', None)\n"
        "print('OK' if not errors else 'FAIL:'+'; '.join(errors))\n"
        "print('ACTION_FORBID', extra)\n"
    )
    try:
        rc, out, err = docker_backend_python(mapper_py)
        ok_line = next((ln for ln in out.splitlines() if ln.startswith("OK") or ln.startswith("FAIL:")), "")
        expect(
            f,
            rc == 0 and ok_line.startswith("OK"),
            "Sysmon + auditd events map to ProcessTreeNode without Pydantic errors",
            detail=ok_line or err.strip()[:400],
            path=tree,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        f.append(
            Finding(
                "WARNING",
                "could not exec backend-api for live Pydantic mapping (docker unavailable)",
                detail=str(exc),
                path=tree,
            )
        )

    # Agent ZIP contents
    try:
        from app.services.agent_package_builder import build_agent_package_zip

        win_data, _ = build_agent_package_zip(
            tenant_name="QA", short_code="QAPLAT", wazuh_agent_group="tenant_QAPLAT", os_type="windows"
        )
        win_names = set(zipfile.ZipFile(io.BytesIO(win_data)).namelist())
        expect(
            f,
            "windows/sysmon-windows-baseline.xml" in win_names
            and "windows/Enable-MsspWindowsTelemetry.ps1" in win_names,
            "Windows agent ZIP includes Sysmon baseline + telemetry installer",
            path=builder,
        )
        lnx_data, _ = build_agent_package_zip(
            tenant_name="QA", short_code="QAPLAT", wazuh_agent_group="tenant_QAPLAT", os_type="linux"
        )
        lnx_names = set(zipfile.ZipFile(io.BytesIO(lnx_data)).namelist())
        expect(
            f,
            "linux/install-mssp-linux-telemetry.sh" in lnx_names and "linux/mssp-exec.rules" in lnx_names,
            "Linux agent ZIP includes auditd helper + execve rules",
            path=builder,
        )
    except Exception as exc:
        f.append(
            Finding("FAILED", "could not generate agent ZIPs", detail=f"{type(exc).__name__}: {exc}", path=builder)
        )

    _check_wazuh_rule_ids(f)
    return cr


def _iter_rule_xml() -> Iterable[Path]:
    for folder in (
        ROOT / "deploy" / "wazuh-rules",
        ROOT / "deploy" / "wazuh-manager",
        ROOT / "ansible" / "roles" / "mssp_linux_midlayer" / "files",
    ):
        if folder.is_dir():
            yield from folder.glob("*.xml")


def _check_wazuh_rule_ids(findings: List[Finding]) -> None:
    canonical = ROOT / "deploy" / "wazuh-manager" / "mssp_linux_exec_rules.xml"
    alt = ROOT / "deploy" / "wazuh-rules"
    if alt.is_dir() and any(alt.glob("*.xml")):
        findings.append(Finding("PASSED", "deploy/wazuh-rules/ contains Manager XML", path=alt))
    else:
        findings.append(
            Finding(
                "PASSED",
                "MSSP Wazuh rules live in deploy/wazuh-manager/ (not deploy/wazuh-rules/)",
                detail="scan covers wazuh-manager + Ansible role copy",
                path=canonical,
            )
        )
    xml_files = list(_iter_rule_xml())
    if not xml_files:
        findings.append(Finding("FAILED", "no Wazuh Manager XML rules found under deploy/", path=canonical))
        return
    id_rx = re.compile(r'<rule\s+id="(\d+)"')
    seen: Dict[int, Path] = {}
    for path in xml_files:
        text = read(path)
        for match in id_rx.finditer(text):
            rid = int(match.group(1))
            if rid in FORBIDDEN_RULE_IDS:
                findings.append(
                    Finding(
                        "FAILED",
                        f"rule id {rid} reuses a reserved upstream/custom ID",
                        path=path,
                    )
                )
                continue
            if not (MSSP_RULE_ID_MIN <= rid <= MSSP_RULE_ID_MAX):
                findings.append(
                    Finding(
                        "FAILED",
                        f"MSSP-owned rule id {rid} is outside {MSSP_RULE_ID_MIN}-{MSSP_RULE_ID_MAX}",
                        path=path,
                    )
                )
                continue
            seen[rid] = path
    expect(
        findings,
        110001 in seen and 110005 in seen,
        "Linux execve high-signal rules 110001-110005 present",
        path=canonical,
        pattern=r'rule id="110001"',
    )
    if seen:
        findings.append(
            Finding(
                "PASSED",
                f"{len(seen)} MSSP Wazuh rule IDs in reserved range {MSSP_RULE_ID_MIN}-{MSSP_RULE_ID_MAX}",
            )
        )


# ---------------------------------------------------------------------------
# CHECK 2 — Engine deploy portability + adapters
# ---------------------------------------------------------------------------
LAB_IP_RX = re.compile(r"192\.168\.0\.\d+")
VM_ID_ASSERT_RX = re.compile(r"\(vm_id\s*\|\s*int\)\s*==\s*\d+")


def check_engines() -> CheckResult:
    cr = CheckResult("CHECK 2: Network & security engines (deploy + adapters)")
    f = cr.findings
    playbooks_dir = ROOT / "ansible" / "playbooks"
    engines_deploy = ROOT / "scripts" / "production_deploy_engines.sh"
    inventory_example = ROOT / "ansible" / "inventory" / "production.example.yml"

    require_file(f, engines_deploy, "production_deploy_engines.sh")
    require_file(f, inventory_example, "production inventory example")
    expect(
        f,
        "MSSP_ANSIBLE_INVENTORY" in read(engines_deploy) and "MSSP_ENGINE_DEPLOY_APPROVED" in read(engines_deploy),
        "engine deploy is inventory/env gated (not a blind install)",
        path=engines_deploy,
        pattern=r"MSSP_ANSIBLE_INVENTORY",
    )

    for engine in ENGINE_CATALOG:
        name = engine["name"]
        pb = engine["playbook"]
        if pb is None:
            f.append(
                Finding(
                    "GAP",
                    f"{name}: no dedicated Ansible install playbook",
                    detail=str(engine.get("gap_reason") or "add playbooks/<engine>.yml and assert it here"),
                    path=playbooks_dir,
                )
            )
        elif pb.is_file():
            f.append(Finding("PASSED", f"{name}: playbook present", path=pb))
            body = read(pb)
            if LAB_IP_RX.search(body):
                f.append(
                    Finding(
                        "GAP",
                        f"{name}: playbook contains hardcoded 192.168.0.x (must be inventory-only)",
                        path=pb,
                        line=locate(pb, r"192\.168\.0\."),
                    )
                )
            else:
                f.append(Finding("PASSED", f"{name}: playbook has no hardcoded lab IPs", path=pb))
        else:
            f.append(
                Finding(
                    "FAILED" if engine["live_required"] else "GAP",
                    f"{name}: playbook missing",
                    detail=str(engine.get("gap_reason") or ""),
                    path=pb,
                )
            )

        missing_adapters = [p for p in engine["adapters"] if not p.is_file()]
        if missing_adapters:
            f.append(
                Finding(
                    "FAILED",
                    f"{name}: adapter file missing",
                    detail=", ".join(str(p.relative_to(ROOT)) for p in missing_adapters),
                )
            )
        else:
            f.append(Finding("PASSED", f"{name}: API/client adapter files exist"))

        persist_ok = any(engine["persist"] in read(p) for p in engine["adapters"] if p.is_file())
        expect(
            f,
            persist_ok,
            f"{name}: database persistence method exists ({engine['persist']})",
            path=engine["adapters"][-1],
            pattern=re.escape(engine["persist"].split()[-1]),
        )

    expect(
        f,
        "playbooks/misp.yml" in read(engines_deploy) and "playbooks/zeek.yml" in read(engines_deploy),
        "engine deploy order includes Zeek and MISP playbooks",
        path=engines_deploy,
        pattern=r"playbooks/misp.yml",
    )
    expect(
        f,
        "playbooks/velociraptor.yml" in read(engines_deploy),
        "engine deploy order includes Velociraptor playbook",
        path=engines_deploy,
        pattern=r"playbooks/velociraptor.yml",
    )
    inv_ex = read(inventory_example)
    expect(
        f,
        "threat_intel:" in inv_ex and "deployment_role: misp" in inv_ex,
        "production inventory example includes MISP (threat_intel)",
        path=inventory_example,
        pattern=r"threat_intel:",
    )
    expect(
        f,
        "dfir:" in inv_ex and "deployment_role: velociraptor" in inv_ex,
        "production inventory example includes Velociraptor (dfir)",
        path=inventory_example,
        pattern=r"deployment_role: velociraptor",
    )
    expect(
        f,
        "windows-endpoint-lab:" in inv_ex and "deployment_role: wazuh_agent_windows" in inv_ex,
        "production inventory example includes Windows agent host",
        path=inventory_example,
        pattern=r"wazuh_agent_windows",
    )

    # Lab VM-ID identity locks must stay gone (cloud inventory uses ansible_host).
    roles = ROOT / "ansible" / "roles"
    locked: List[Tuple[Path, int]] = []
    if roles.is_dir():
        for path in roles.glob("*/tasks/main.yml"):
            line = locate(path, r"\(vm_id\s*\|\s*int\)\s*==\s*\d+")
            if line:
                locked.append((path, line))
    if locked:
        detail = "; ".join(f"{p.relative_to(ROOT)}:{ln}" for p, ln in locked[:12])
        f.append(
            Finding(
                "GAP",
                f"{len(locked)} Ansible roles still assert lab vm_id identity (cloud inventory must spoof IDs)",
                detail=detail,
                path=ROOT / "ansible" / "inventory" / "production.example.yml",
            )
        )
    else:
        f.append(Finding("PASSED", "no Ansible role asserts a lab vm_id"))
        expect(
            f,
            "wazuh_manager_ip" in read(ROOT / "ansible" / "group_vars" / "all.yml"),
            "group_vars resolve wazuh_manager_ip from inventory wazuh_stack",
            path=ROOT / "ansible" / "group_vars" / "all.yml",
            pattern=r"wazuh_manager_ip",
        )

    midlayer = ROOT / "ansible" / "playbooks" / "mssp-linux-midlayer-manager.yml"
    mid_role = ROOT / "ansible" / "roles" / "mssp_linux_midlayer" / "tasks" / "main.yml"
    expect(
        f,
        midlayer.is_file() and "vm_id" not in read(mid_role),
        "Linux mid-layer Manager playbook is cloud-portable (no vm_id assert)",
        path=midlayer,
    )
    if playbooks_dir.is_dir():
        for pb in sorted(playbooks_dir.glob("*.yml")):
            code = "\n".join(
                ln for ln in read(pb).splitlines() if not ln.lstrip().startswith("#")
            )
            if LAB_IP_RX.search(code):
                f.append(
                    Finding(
                        "GAP",
                        f"{pb.name}: hardcoded 192.168.0.x in playbook (use inventory/env)",
                        path=pb,
                        line=locate(pb, r"192\.168\.0\."),
                    )
                )
    return cr


# ---------------------------------------------------------------------------
# CHECK 3 — Backend routes, schema, source_tool labels
# ---------------------------------------------------------------------------
def _sql_tables() -> Set[str]:
    names: Set[str] = set()
    init = ROOT / "postgres" / "init"
    rx = re.compile(r"CREATE TABLE IF NOT EXISTS\s+([a-z_][a-z0-9_]*)", re.I)
    if init.is_dir():
        for path in init.glob("*.sql"):
            names.update(rx.findall(read(path)))
    return names


def _sql_refs_in_python(path: Path) -> Set[str]:
    """Extract table names from SQL in triple-quoted strings only (not Python imports)."""
    text = read(path)
    blobs = re.findall(r'"""(.*?)"""', text, re.S)
    blobs += re.findall(r"'''(.*?)'''", text, re.S)
    found: Set[str] = set()
    sql_rx = re.compile(
        r"\b(?:FROM|JOIN|INTO)\s+(?:ONLY\s+)?(?:LATERAL\s+)?([a-z_][a-z0-9_]*)",
        re.I,
    )
    update_rx = re.compile(r"^\s*UPDATE\s+([a-z_][a-z0-9_]*)", re.I | re.M)
    for blob in blobs:
        cleaned = re.sub(r"--.*?$", "", blob, flags=re.M)
        cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.S)
        if not re.search(r"\b(SELECT|INSERT|UPDATE|DELETE)\b", cleaned, re.I):
            continue
        found.update(m.lower() for m in sql_rx.findall(cleaned))
        found.update(m.lower() for m in update_rx.findall(cleaned))
    return found


def check_backend_schemas() -> CheckResult:
    cr = CheckResult("CHECK 3: Backend control plane & security schemas")
    f = cr.findings
    labels = BACKEND / "app" / "services" / "customer_safe_labels.py"
    taxonomy = BACKEND / "app" / "services" / "soc_alert_taxonomy.py"
    main_py = BACKEND / "app" / "main.py"
    require_file(f, labels, "customer_safe_labels.py")
    require_file(f, taxonomy, "soc_alert_taxonomy.py")
    require_file(f, main_py, "main.py router wiring")

    # Import mapping without spinning FastAPI (avoids JWT_SECRET at import of unused auth).
    sys.path.insert(0, str(BACKEND))
    try:
        from app.services.customer_safe_labels import customer_safe_alert_source
        from app.services.soc_alert_taxonomy import derive_asset_category
    except Exception as exc:
        f.append(Finding("FAILED", "could not import label/taxonomy modules", detail=str(exc), path=labels))
        return cr

    mapping_src = ast.parse(read(labels))
    mapping_keys: Set[str] = set()
    for node in ast.walk(mapping_src):
        if isinstance(node, ast.Dict):
            for k in node.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    mapping_keys.add(k.value)

    for tool in REQUIRED_SOURCE_TOOLS:
        label = customer_safe_alert_source(tool)
        expect(
            f,
            bool(label) and label.lower() != tool,
            f"customer_safe_labels maps source_tool={tool!r} to a customer-safe capability label",
            path=labels,
            detail=f"label={label!r}",
            status_if_false="FAILED",
        )
        if tool not in mapping_keys and tool not in ("manual", "platform"):
            f.append(
                Finding(
                    "FAILED",
                    f"source_tool={tool!r} is not an explicit key in customer_safe_labels mapping",
                    detail="unknown tools fall through to generic 'Managed detection' — add an explicit capability label",
                    path=labels,
                )
            )
        try:
            slug, device = derive_asset_category({"source_tool": tool, "raw_event": {}})
            expect(
                f,
                bool(slug),
                f"soc_alert_taxonomy handles source_tool={tool!r} without raising",
                path=taxonomy,
                detail=f"asset_category={slug} device_type={device}",
            )
        except Exception as exc:
            f.append(
                Finding(
                    "FAILED",
                    f"soc_alert_taxonomy raised for source_tool={tool!r}",
                    detail=str(exc),
                    path=taxonomy,
                )
            )

    # FastAPI route inventory
    try:
        rc, out, err = docker_backend_python(
            "from app.main import app\n"
            "routes=[]\n"
            "for r in app.routes:\n"
            "    methods=getattr(r,'methods',None) or set()\n"
            "    path=getattr(r,'path',None)\n"
            "    if path:\n"
            "        routes.append((path, ','.join(sorted(methods))))\n"
            "print('\\n'.join(p+' '+m for p,m in routes))\n"
        )
        routes = {}
        if rc == 0:
            for line in out.splitlines():
                if not line.strip():
                    continue
                parts = line.rsplit(" ", 1)
                if len(parts) == 2:
                    routes.setdefault(parts[0], set()).update(parts[1].split(","))
            f.append(Finding("PASSED", f"FastAPI app loaded ({len(routes)} paths)", path=main_py))
            for path, method in REQUIRED_ROUTES:
                methods = routes.get(path, set())
                # FastAPI may register path params with different names.
                match = path in routes or any(
                    _path_template_matches(existing, path) for existing in routes
                )
                expect(
                    f,
                    match,
                    f"route {method} {path} is registered",
                    path=main_py,
                    detail="" if match else "missing from app.routes — add it and extend REQUIRED_ROUTES",
                )
        else:
            f.append(
                Finding(
                    "WARNING",
                    "could not load FastAPI app inside backend-api for route inventory",
                    detail=(err or out)[:400],
                    path=main_py,
                )
            )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        f.append(Finding("WARNING", "docker compose exec unavailable for route inventory", detail=str(exc)))

    tables = _sql_tables()
    expect(f, "security_alerts" in tables and "edr_process_events" in tables, "core EDR/SOC tables exist in postgres/init")
    expect(f, "tenant_ndr_events" in tables, "NDR events table exists")
    expect(f, "tenant_threat_intel_iocs" in tables, "threat-intel IOC table exists")
    expect(f, "tenant_forensics_collections" in tables, "forensics collections table exists")

    sql_keywords = {
        "select", "where", "and", "or", "as", "on", "set", "values", "into", "from",
        "join", "left", "right", "inner", "outer", "true", "false", "null", "not",
        "case", "when", "then", "else", "end", "limit", "offset", "order", "group",
        "having", "union", "exists", "in", "is", "like", "between", "distinct",
        "count", "coalesce", "uuid", "text", "jsonb", "now", "excluded", "lateral",
        "only", "rows", "with", "recursive",
    }
    core_unscored = {"tenants", "appliances", "incidents", "vulnerabilities"}
    orphans: List[str] = []
    routes_dir = BACKEND / "app" / "api" / "routes"
    for path in sorted(routes_dir.glob("*.py")):
        for table in _sql_refs_in_python(path):
            if table in sql_keywords or table in tables:
                continue
            if table.startswith("pg_") or table in {"information_schema", "generate_series"}:
                continue
            # Skip English/column tokens: real MSSP tables are underscored or core_unscored.
            if "_" not in table and table not in core_unscored:
                continue
            orphans.append(f"{path.name}:{table}")
    if orphans:
        f.append(
            Finding(
                "FAILED",
                "route SQL references tables not created in postgres/init",
                detail="; ".join(orphans[:20]),
                path=routes_dir,
            )
        )
    else:
        f.append(Finding("PASSED", "no orphaned SQL table names in API route modules"))
    return cr


def _path_template_matches(existing: str, required: str) -> bool:
    def norm(p: str) -> str:
        return re.sub(r"\{[^}]+\}", "{}", p)

    return norm(existing) == norm(required)


# ---------------------------------------------------------------------------
# CHECK 4 — Portability / cloud readiness
# ---------------------------------------------------------------------------
def check_portability() -> CheckResult:
    cr = CheckResult("CHECK 4: Portability & cloud readiness")
    f = cr.findings
    deploy_sh = ROOT / "scripts" / "production_deploy_control_plane.sh"
    cache_sh = ROOT / "scripts" / "cache_sysmon_offline.sh"
    checklist = ROOT / "deploy" / "RELEASE_CHECKLIST.md"
    docs_checklist = ROOT / "docs" / "RELEASE_CHECKLIST.md"
    kb094 = ROOT / "docs" / "KB094_PRODUCTION_PORTABILITY_PACK.md"
    require_file(f, deploy_sh, "production_deploy_control_plane.sh")
    require_file(f, cache_sh, "cache_sysmon_offline.sh")
    require_file(f, checklist, "deploy/RELEASE_CHECKLIST.md")
    expect(
        f,
        "cache_sysmon_offline" in read(deploy_sh) and "MSSP_SKIP_SYSMON_CACHE" in read(deploy_sh),
        "control-plane deploy caches Sysmon64.exe with an explicit skip/fallback",
        path=deploy_sh,
        pattern=r"cache_sysmon_offline",
    )
    sysmon = BACKEND / "app" / "endpoint_configs" / "Sysmon64.exe"
    if sysmon.is_file():
        f.append(Finding("PASSED", "Sysmon64.exe is cached on this control plane (gitignored)", path=sysmon))
    else:
        f.append(
            Finding(
                "WARNING",
                "Sysmon64.exe not cached here — deploy script must download or operator must copy it",
                detail="never commit the binary; run scripts/cache_sysmon_offline.sh",
                path=cache_sh,
            )
        )
    expect(
        f,
        "verify_platform_state.py" in read(checklist),
        "deploy/RELEASE_CHECKLIST.md requires verify_platform_state.py",
        path=checklist,
        pattern=r"verify_platform_state.py",
    )
    expect(
        f,
        docs_checklist.is_file() and "verify_platform_state.py" in read(docs_checklist),
        "docs/RELEASE_CHECKLIST.md points at the master verifier",
        path=docs_checklist,
        pattern=r"verify_platform_state.py",
    )
    expect(
        f,
        "verify_platform_state.py" in read(kb094),
        "KB-094 documents the master verifier as mandatory before cloud deploy",
        path=kb094,
        pattern=r"verify_platform_state.py",
    )
    expect(
        f,
        "CRITICAL RULE" in read(Path(__file__)),
        "this script header still instructs agents to extend assertions on architecture changes",
        path=Path(__file__),
        pattern=r"CRITICAL RULE",
    )
    return cr


# ---------------------------------------------------------------------------
# CHECK 5 — Appliance license mint / verify / bake
# ---------------------------------------------------------------------------
def check_appliance_licensing() -> CheckResult:
    cr = CheckResult("CHECK 5: Appliance cryptographic licensing")
    f = cr.findings
    mint = BACKEND / "app" / "services" / "junexis_license.py"
    sync = BACKEND / "app" / "services" / "appliance_entitlement_sync.py"
    ops = ROOT / "kevantic-appliance" / "cli" / "kevantic-cli" / "kevantic_cli" / "license_ops.py"
    register = ROOT / "kevantic-appliance" / "cli" / "kevantic-cli" / "kevantic_cli" / "register_ops.py"
    pub = ROOT / "kevantic-appliance" / "licensing" / "keys" / "licensing-ed25519-v1.pub"
    role_pub = (
        ROOT
        / "kevantic-appliance"
        / "ansible"
        / "roles"
        / "license_enforcer"
        / "files"
        / "licensing-ed25519-v1.pub"
    )
    timer = ROOT / "kevantic-appliance" / "configs" / "systemd" / "kevantic-license-enforce.timer"
    unit = ROOT / "kevantic-appliance" / "configs" / "systemd" / "kevantic-license-enforce.service"
    kb093g = ROOT / "scripts" / "kb093g_validate_appliance_install_iso.sh"
    bake = ROOT / "kevantic-appliance" / "scripts" / "bake_golden_vm199_fleet_reporting.sh"

    require_file(f, mint, "junexis_license.py")
    require_file(f, sync, "appliance_entitlement_sync.py")
    require_file(f, ops, "license_ops.py")
    require_file(f, register, "register_ops.py")
    require_file(f, pub, "licensing-ed25519-v1.pub")
    require_file(f, role_pub, "license_enforcer files/licensing-ed25519-v1.pub")
    require_file(f, timer, "kevantic-license-enforce.timer")
    require_file(f, unit, "kevantic-license-enforce.service")

    mint_txt = read(mint)
    ops_txt = read(ops)
    sync_txt = read(sync)
    reg_txt = read(register)
    expect(
        f,
        'ISSUER = "kevantic-license"' in mint_txt,
        "mint ISSUER is kevantic-license",
        path=mint,
        pattern=r'ISSUER = "kevantic-license"',
    )
    expect(
        f,
        'LICENSE_ISSUER = "kevantic-license"' in ops_txt,
        "appliance verify issuer is kevantic-license",
        path=ops,
        pattern=r'LICENSE_ISSUER = "kevantic-license"',
    )
    expect(
        f,
        "KEVANTIC_LICENSE_PRIVATE_KEY_PEM" in mint_txt
        and "JUNEXIS_LICENSE_PRIVATE_KEY_PEM" in mint_txt,
        "signing env accepts KEVANTIC_ and JUNEXIS_ private-key aliases",
        path=mint,
        pattern=r"KEVANTIC_LICENSE_PRIVATE_KEY_PEM",
    )
    expect(
        f,
        "from app.services.junexis_license import" in read(kb093g),
        "kb093g imports junexis_license",
        path=kb093g,
        pattern=r"from app.services.junexis_license import",
    )
    expect(
        f,
        "mint_license(" in sync_txt and '"license_jws"' in sync_txt,
        "entitlement sync mints a signed license_jws per appliance",
        path=sync,
        pattern=r"mint_license",
    )
    expect(
        f,
        "license_jws required" in reg_txt,
        "heartbeat apply_entitlements rejects unsigned JSON and requires license_jws",
        path=register,
        pattern=r"license_jws required",
    )
    expect(
        f,
        "def enforce_license" in ops_txt
        and "/etc/kevantic/trust/keys/licensing-ed25519-v1.pub" in ops_txt,
        "license_ops.enforce_license re-verifies using the baked public key",
        path=ops,
        pattern=r"def enforce_license",
    )
    expect(
        f,
        "python3 -m kevantic_cli license enforce" in read(unit),
        "license enforce unit runs kevantic-cli license enforce",
        path=unit,
        pattern=r"license enforce",
    )
    expect(
        f,
        "licensing-ed25519-v1.pub" in read(bake)
        and "kevantic-license-enforce.timer" in read(bake),
        "golden bake installs pubkey and license enforce timer",
        path=bake,
        pattern=r"licensing-ed25519-v1.pub",
    )
    expect(
        f,
        pub.is_file() and b"BEGIN PUBLIC KEY" in pub.read_bytes(),
        "baked Ed25519 public key is PEM",
        path=pub,
    )

    try:
        from app.services.junexis_license import (  # noqa: WPS433
            ISSUER,
            generate_keypair,
            mint_license,
            verify_license,
        )
        from cryptography.hazmat.primitives.serialization import load_pem_private_key

        assert ISSUER == "kevantic-license"
        priv_pem, pub_pem = generate_keypair()
        key = load_pem_private_key(priv_pem, password=None)
        minted = mint_license(
            tenant_id="11111111-1111-1111-1111-111111111111",
            service_ids=["svc-01", "svc-06"],
            appliance_id="22222222-2222-2222-2222-222222222222",
            core=True,
            private_key=key,
        )
        claims = verify_license(minted["license_jws"], public_key_pem=pub_pem)
        ok = claims.get("iss") == "kevantic-license" and "svc-01" in claims.get("svc", [])
        expect(f, ok, "ephemeral mint/verify round-trip uses kevantic-license")
    except Exception as exc:  # noqa: BLE001
        f.append(
            Finding(
                "FAILED",
                "ephemeral mint/verify round-trip uses kevantic-license",
                detail=str(exc)[:240],
                path=mint,
            )
        )
    return cr


# ---------------------------------------------------------------------------
# CHECK 6 — Open-source compliance attributions + UI brand isolation
# ---------------------------------------------------------------------------
FORBIDDEN_UI_ENGINE_NAMES = re.compile(
    r"\b(Wazuh|Suricata|Zeek|Nuclei|Vuls|Greenbone|Velociraptor|Fluent\s*Bit|TheHive|Shuffle|MISP|OpenVAS)\b",
    re.I,
)


def _tsx_line_exposes_engine_brand(line: str) -> bool:
    stripped = line.strip()
    if stripped.startswith("//") or stripped.startswith("*"):
        return False
    # Internal API/filter enum keys — not rendered UI copy.
    if re.search(
        r'\bvalue:\s*["\'](?:wazuh|suricata|zeek|nuclei|vuls|greenbone|velociraptor|misp|shuffle|thehive|openvas)["\']',
        line,
        re.I,
    ):
        return False
    # Schema field names (wazuh_rule_id, thehive_case_id, …) are not product branding.
    scrubbed = re.sub(
        r"\b(?:wazuh|thehive|greenbone|nuclei|vuls|shuffle|suricata|zeek|velociraptor|misp|openvas)_[a-z0-9_]+\b",
        "",
        line,
        flags=re.I,
    )
    return bool(FORBIDDEN_UI_ENGINE_NAMES.search(scrubbed))


def check_open_source_compliance() -> CheckResult:
    cr = CheckResult("CHECK 6: Open-source compliance & UI brand isolation")
    f = cr.findings
    repo_attrib = ROOT / "ATTRIBUTIONS.md"
    appliance_attrib = ROOT / "kevantic-appliance" / "ATTRIBUTIONS.txt"
    build_sh = ROOT / "kevantic-appliance" / "mkosi" / "build.sh"
    runtime_tasks = (
        ROOT / "kevantic-appliance" / "ansible" / "roles" / "kevantic_runtime" / "tasks" / "main.yml"
    )
    postinst = ROOT / "kevantic-appliance" / "mkosi" / "mkosi.postinst"

    require_file(f, repo_attrib, "repository ATTRIBUTIONS.md")
    require_file(f, appliance_attrib, "appliance ATTRIBUTIONS.txt")
    require_file(f, build_sh, "mkosi build.sh")
    require_file(f, runtime_tasks, "kevantic_runtime tasks")
    require_file(f, postinst, "mkosi.postinst")

    build_txt = read(build_sh)
    runtime_txt = read(runtime_tasks)
    postinst_txt = read(postinst)
    attrib_txt = read(appliance_attrib)

    for needle in ("GPL-2.0", "Apache License 2.0", "AGPL-3.0", "BSD 3-Clause", "MIT License"):
        expect(
            f,
            needle in attrib_txt,
            f"appliance ATTRIBUTIONS.txt mentions {needle}",
            path=appliance_attrib,
            pattern=re.escape(needle),
        )

    expect(
        f,
        "usr/share/doc/kevantic/ATTRIBUTIONS.txt" in build_txt,
        "mkosi build.sh stages ATTRIBUTIONS.txt under /usr/share/doc/kevantic/",
        path=build_sh,
        pattern=r"usr/share/doc/kevantic/ATTRIBUTIONS\.txt",
    )
    expect(
        f,
        "/usr/share/doc/kevantic/ATTRIBUTIONS.txt" in runtime_txt,
        "kevantic_runtime installs /usr/share/doc/kevantic/ATTRIBUTIONS.txt",
        path=runtime_tasks,
        pattern=r"/usr/share/doc/kevantic/ATTRIBUTIONS\.txt",
    )
    expect(
        f,
        "/usr/share/doc/kevantic/ATTRIBUTIONS.txt" in postinst_txt,
        "mkosi.postinst asserts baked ATTRIBUTIONS.txt exists",
        path=postinst,
        pattern=r"/usr/share/doc/kevantic/ATTRIBUTIONS\.txt",
    )

    ui_roots = (ROOT / "frontend-admin" / "src", ROOT / "frontend-customer" / "src")
    violations: List[str] = []
    for ui_root in ui_roots:
        if not ui_root.is_dir():
            continue
        for path in sorted(ui_root.rglob("*.tsx")):
            rel = path.relative_to(ROOT)
            for idx, line in enumerate(read(path).splitlines(), start=1):
                if _tsx_line_exposes_engine_brand(line):
                    violations.append(f"{rel}:{idx}: {line.strip()[:120]}")
    expect(
        f,
        not violations,
        "customer/admin .tsx UI files contain no upstream engine product names",
        detail="; ".join(violations[:8]) + (" …" if len(violations) > 8 else ""),
        status_if_false="FAILED",
    )
    if not violations:
        f.append(
            Finding(
                "PASSED",
                "customer/admin .tsx UI files contain no upstream engine product names",
                path=ui_roots[0],
            )
        )
    return cr


def main() -> int:
    parser = argparse.ArgumentParser(description="MSSP platform master verifier")
    parser.add_argument(
        "--release",
        action="store_true",
        help="treat GAP findings as failures (required for production/cloud cutover)",
    )
    args = parser.parse_args()

    print(f"{BOLD}MSSP platform state verification{RESET}")
    print(f"root={ROOT}")
    if args.release:
        print("mode=release (GAP counts as failure)")
    print()

    checks = [
        check_edr_pipeline(),
        check_engines(),
        check_backend_schemas(),
        check_portability(),
        check_appliance_licensing(),
        check_open_source_compliance(),
    ]

    passed = failed = warnings = gaps = 0
    for cr in checks:
        failed_here = cr.failed
        stamp = f"{RED}FAILED{RESET}" if failed_here else f"{GREEN}PASSED{RESET}"
        if cr.gaps and not failed_here:
            stamp = f"{MAGENTA}GAPS{RESET}"
        print(f"{BOLD}{cr.name}{RESET}  [{stamp}]")
        for finding in cr.findings:
            print(finding.render())
            if finding.status == "PASSED":
                passed += 1
            elif finding.status == "FAILED":
                failed += 1
            elif finding.status == "WARNING":
                warnings += 1
            elif finding.status == "GAP":
                gaps += 1
        print()

    print(
        f"{BOLD}Summary{RESET}  PASSED {passed}  WARNING {warnings}  GAP {gaps}  FAILED {failed}"
    )
    cloud_ready = failed == 0 and gaps == 0
    print(f"CLOUD-READY: {'YES' if cloud_ready else 'NO'}")
    if failed:
        print("RESULT: FAILED")
        return 1
    if args.release and gaps:
        print("RESULT: FAILED (release mode — close GAPs or do not declare cloud-complete)")
        return 1
    print("RESULT: PASSED" + (" (documented GAPs remain — not cloud-complete)" if gaps else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
