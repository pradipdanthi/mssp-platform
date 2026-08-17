"""Execute local catalogue jobs (IR / containment / IOC / forensics / EASM / ITDR)."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Tuple

from appliance.common.paths import ensure_engine_dirs, state_root
from appliance.hunting.retrospective_sweeper import RetrospectiveSweeper

logger = logging.getLogger(__name__)


def _engine_bin(name: str) -> Path:
    return Path(os.environ.get("KEVANTIC_ENGINE_BIN", "/opt/kevantic/engines/bin")) / name


def execute_job(svc: str, job_type: str, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    ensure_engine_dirs()
    handlers = {
        "svc-02": _exec_ir,
        "svc-03": _exec_containment,
        "svc-07": _exec_threat_intel,
        "svc-08": _exec_forensics,
        "svc-09": _exec_easm,
        "svc-10": _exec_itdr,
    }
    fn = handlers.get(svc)
    if not fn:
        return False, {"error": f"no executor for {svc}"}
    try:
        return fn(job_type, payload)
    except Exception as exc:  # noqa: BLE001
        logger.exception("job failed svc=%s type=%s", svc, job_type)
        return False, {"error": str(exc)[:400]}


def _exec_ir(job_type: str, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """Incident Response local execution — collect evidence / stage bundle."""
    action = (job_type or payload.get("action") or "collect_evidence").lower()
    agent_id = str(payload.get("agent_id") or "")
    out_dir = state_root() / "ir" / time.strftime("%Y%m%dT%H%M%SZ")
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "action": action,
        "agent_id": agent_id,
        "requested": payload,
        "staged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "note": "Evidence staging complete; raw logs stay local until signed upload policy",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return True, {"staged_dir": str(out_dir), "manifest": manifest}


def _exec_containment(job_type: str, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """Run Active Response against local Manager (same path as heartbeat job pull)."""
    agent_id = str(payload.get("agent_id") or "")
    command = str(payload.get("ar_command") or payload.get("command") or "")
    arguments = payload.get("arguments") or []
    if not agent_id or not command:
        return False, {"error": "agent_id and ar_command required"}
    try:
        from kevantic_cli.register_ops import (  # type: ignore
            _authenticate_local_wazuh,
            _ensure_local_edr_ar_commands,
            _wazuh_local_json,
        )
    except ImportError:
        from junexis_cli.register_ops import (  # type: ignore
            _authenticate_local_wazuh,
            _ensure_local_edr_ar_commands,
            _wazuh_local_json,
        )
    _ensure_local_edr_ar_commands()
    token = _authenticate_local_wazuh()
    cmd = command if command.startswith("!") else f"!{command}"
    result = _wazuh_local_json(
        "PUT",
        f"/active-response?agents_list={agent_id}",
        body={"command": cmd, "arguments": [str(a) for a in arguments]},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    data = result.get("data") or {}
    if int(data.get("total_failed_items") or 0) > 0 or int(result.get("error") or 0) != 0:
        failed = data.get("failed_items") or []
        detail = ""
        if failed and isinstance(failed[0], dict):
            err = failed[0].get("error") or {}
            detail = str(err.get("message") or failed[0])[:300]
        return False, {"error": detail or f"Active response failed for agent {agent_id}"}
    return True, {"dispatched": True, "agent_id": agent_id, "command": command}


def _exec_threat_intel(job_type: str, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """IOC cache + retrospective hunt via DuckDB lake."""
    action = (job_type or "hunt").lower()
    cache_dir = state_root() / "ioc-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    if action in ("cache_push", "ioc_push"):
        iocs = payload.get("iocs") or []
        path = cache_dir / f"ioc-{int(time.time())}.json"
        path.write_text(json.dumps({"iocs": iocs, "meta": payload.get("meta") or {}}, indent=2) + "\n")
        return True, {"cached": str(path), "count": len(iocs)}
    # default: retrospective hunt
    sweeper = RetrospectiveSweeper()
    result = sweeper.run_job(
        {
            "job_id": payload.get("job_id") or f"local-{int(time.time())}",
            "iocs": payload.get("iocs") or [],
            "lookback_days": int(payload.get("lookback_days") or 30),
        }
    )
    return True, result


def _exec_forensics(job_type: str, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    agent_id = str(payload.get("agent_id") or "unknown")
    out = state_root() / "forensics" / agent_id / time.strftime("%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True, exist_ok=True)
    meta = {
        "agent_id": agent_id,
        "requested_artifacts": payload.get("artifacts") or ["triage"],
        "staged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (out / "request.json").write_text(json.dumps(meta, indent=2) + "\n")
    return True, {"staged_dir": str(out), "status": "awaiting_agent_upload"}


def _exec_easm(job_type: str, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    targets = payload.get("targets") or []
    templates = payload.get("templates") or ["http/technologies"]
    nuclei = _engine_bin("nuclei")
    if not targets:
        return False, {"error": "targets required"}
    if not nuclei.is_file():
        return False, {"error": "nuclei binary missing"}
    out = state_root() / "easm" / time.strftime("%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True, exist_ok=True)
    target_file = out / "targets.txt"
    target_file.write_text("\n".join(str(t) for t in targets) + "\n")
    result_file = out / "nuclei.jsonl"
    cmd = [
        str(nuclei),
        "-l",
        str(target_file),
        "-jsonl",
        "-o",
        str(result_file),
        "-silent",
    ]
    for t in templates:
        cmd.extend(["-t", str(t)])
    # Cap runtime for appliance safety
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=int(payload.get("timeout_sec") or 120))
        return True, {
            "exit_code": proc.returncode,
            "result_file": str(result_file),
            "stdout_tail": (proc.stdout or "")[-500:],
            "stderr_tail": (proc.stderr or "")[-500:],
        }
    except subprocess.TimeoutExpired:
        return False, {"error": "nuclei timed out", "result_file": str(result_file)}


def _exec_itdr(job_type: str, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """Identity threat detection connector status / sync stub (IdP hooks)."""
    connector = str(payload.get("connector") or "generic")
    status_dir = state_root() / "itdr"
    status_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "connector": connector,
        "action": job_type or "sync",
        "config_keys": sorted((payload.get("config") or {}).keys()),
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "configured" if payload.get("config") else "awaiting_config",
    }
    path = status_dir / f"{connector}.json"
    path.write_text(json.dumps(record, indent=2) + "\n")
    return True, record
