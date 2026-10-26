"""Live Proxmox hypervisor inventory for Tia (vCPU, RAM, status per MSSP VM)."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Canonical lab map — labels Tia can quote when boss asks about a stack node.
_VM_CATALOG: List[Dict[str, Any]] = [
    {"vmid": 100, "name": "mssp-control", "role": "Control plane", "engine_ids": ["control_plane"]},
    {"vmid": 101, "name": "wazuh-stack", "role": "Wazuh Manager", "engine_ids": ["wazuh"]},
    {
        "vmid": 102,
        "name": "thehive-shuffle",
        "role": "TheHive + Shuffle",
        "engine_ids": ["thehive", "shuffle"],
    },
    {"vmid": 106, "name": "suricata-sensor", "role": "Suricata + Zeek", "engine_ids": ["suricata", "zeek"]},
    {"vmid": 108, "name": "misp", "role": "MISP / threat intel", "engine_ids": ["misp"]},
    {"vmid": 109, "name": "greenbone", "role": "Vuln / EASM", "engine_ids": ["greenbone"]},
    {"vmid": 110, "name": "velociraptor", "role": "Velociraptor DFIR", "engine_ids": ["velociraptor"]},
    {"vmid": 112, "name": "automation", "role": "Ansible automation", "engine_ids": []},
    {"vmid": 115, "name": "mssp-ai", "role": "AI / Ollama", "engine_ids": []},
    {"vmid": 116, "name": "niktiar-secure-edge", "role": "Secure Edge", "engine_ids": ["secure_edge"]},
    {"vmid": 117, "name": "mssp-soc-agent", "role": "SOC Agent (Tia brain)", "engine_ids": ["soc_agent"]},
]

# One pvesh list (~0.4s) instead of per-VM qm config + status (~12s).
_REMOTE_PY = r"""
import json, os, subprocess
node = os.uname().nodename.split(".")[0]
out = {"node": node, "vms": []}
try:
    raw = subprocess.check_output(
        ["pvesh", "get", f"/nodes/{node}/qemu", "--output-format", "json"],
        text=True,
        timeout=25,
    )
    rows = json.loads(raw or "[]")
except Exception as e:
    print(json.dumps({"error": str(e), "vms": [], "node": node}))
    raise SystemExit(0)
for d in rows if isinstance(rows, list) else []:
    try:
        vmid = int(d.get("vmid"))
    except Exception:
        continue
    mem = int(d.get("mem") or 0)
    maxmem = int(d.get("maxmem") or 0)
    cpus = d.get("cpus")
    row = {
        "vmid": vmid,
        "name": d.get("name"),
        "status": d.get("status"),
        "cpus": cpus,
        "cores": cpus,
        "sockets": 1,
        "memory": str(int(maxmem / (1024 * 1024))) if maxmem else None,
        "cpu_pct": round(float(d.get("cpu") or 0) * 100.0, 1),
        "mem_used_mb": round(mem / (1024 * 1024)),
        "mem_max_mb": round(maxmem / (1024 * 1024)),
        "mem_used_gb": round(mem / (1024 ** 3), 2),
        "mem_max_gb": round(maxmem / (1024 ** 3), 2),
        "uptime_sec": d.get("uptime"),
    }
    if maxmem:
        row["mem_used_pct"] = round(100.0 * mem / maxmem, 1)
    out["vms"].append(row)
print(json.dumps(out, separators=(",", ":")))
"""

_cache: Dict[str, Any] = {"ts": 0.0, "payload": None}
_refreshing = False
_CACHE_TTL = 90.0
_STALE_TTL = 300.0


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def proxmox_enabled() -> bool:
    if _env("PROXMOX_ENABLED", "true").lower() in ("0", "false", "no", "off"):
        return False
    key = _key_path()
    return bool(key and key.is_file())


def _key_path() -> Optional[Path]:
    for cand in (
        _env("PROXMOX_SSH_KEY_FILE"),
        "/run/secrets/proxmox_ssh_key",
        "/opt/mssp-control/.secrets/proxmox_ssh_key",
    ):
        if cand and Path(cand).is_file():
            return Path(cand)
    return None


def _cache_file() -> Path:
    return Path(_env("PROXMOX_METRICS_CACHE", "/var/cache/mssp/proxmox_vm_metrics.json"))


def _ssh_pull() -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    key = _key_path()
    if not key:
        return None, "proxmox_ssh_key_missing"
    host = _env("PROXMOX_SSH_HOST", "192.168.0.191")
    user = _env("PROXMOX_SSH_USER", "root")
    timeout = max(8, min(int(_env("PROXMOX_SSH_TIMEOUT", "25") or "25"), 60))
    cmd = [
        "ssh",
        "-i",
        str(key),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=5",
        "-o",
        "IdentitiesOnly=yes",
        f"{user}@{host}",
        "python3",
        "-",
    ]
    try:
        proc = subprocess.run(
            cmd,
            input=_REMOTE_PY,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return None, "openssh_client_missing"
    except subprocess.TimeoutExpired:
        return None, "proxmox_ssh_timeout"
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "ssh_failed")[:240]
        logger.warning("Proxmox SSH failed rc=%s: %s", proc.returncode, err)
        return None, f"proxmox_ssh_failed:{err}"
    try:
        data = json.loads((proc.stdout or "").strip().splitlines()[-1])
    except Exception as exc:  # noqa: BLE001
        return None, f"proxmox_json_parse:{exc}"
    if not isinstance(data, dict):
        return None, "proxmox_bad_payload"
    return data, None


def _read_file_cache(*, max_age: float = 120.0) -> Optional[Dict[str, Any]]:
    path = _cache_file()
    try:
        if not path.is_file():
            return None
        age = time.time() - path.stat().st_mtime
        if age > max_age:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _background_refresh() -> None:
    """Refresh Proxmox inventory without blocking the request path."""
    global _refreshing
    if _refreshing:
        return
    _refreshing = True

    def _run() -> None:
        global _refreshing
        try:
            gather_proxmox_inventory(force=True, allow_stale=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning("proxmox background refresh failed: %s", exc)
        finally:
            _refreshing = False

    try:
        import threading

        threading.Thread(target=_run, name="proxmox-refresh", daemon=True).start()
    except Exception:  # noqa: BLE001
        _refreshing = False


def _enrich(raw: Dict[str, Any]) -> Dict[str, Any]:
    by_id = {int(v.get("vmid")): v for v in (raw.get("vms") or []) if v.get("vmid") is not None}
    catalog_by_id = {int(c["vmid"]): c for c in _VM_CATALOG}
    vms: List[Dict[str, Any]] = []
    for vmid, meta in sorted(catalog_by_id.items()):
        live = by_id.get(vmid) or {}
        cores = live.get("cores") or live.get("cpus")
        try:
            vcpus = int(live.get("cpus") or cores or 0) * int(live.get("sockets") or 1)
        except (TypeError, ValueError):
            vcpus = None
        try:
            mem_cfg_mb = int(live.get("memory") or live.get("mem_max_mb") or 0)
        except (TypeError, ValueError):
            mem_cfg_mb = None
        vms.append(
            {
                "vmid": vmid,
                "name": live.get("name") or meta["name"],
                "role": meta["role"],
                "engine_ids": meta["engine_ids"],
                "status": live.get("status"),
                "vcpus": vcpus or (int(cores) if str(cores).isdigit() else None),
                "cores": int(cores) if str(cores).isdigit() else cores,
                "sockets": live.get("sockets"),
                "ram_configured_mb": mem_cfg_mb,
                "ram_configured_gb": round(mem_cfg_mb / 1024, 2) if mem_cfg_mb else None,
                "ram_used_mb": live.get("mem_used_mb"),
                "ram_used_gb": live.get("mem_used_gb"),
                "ram_max_gb": live.get("mem_max_gb"),
                "ram_used_pct": live.get("mem_used_pct"),
                "cpu_pct": live.get("cpu_pct"),
                "uptime_sec": live.get("uptime_sec"),
            }
        )

    # Also include any extra VMs not in catalog (brief).
    extras = []
    for vmid, live in by_id.items():
        if vmid in catalog_by_id:
            continue
        extras.append(
            {
                "vmid": vmid,
                "name": live.get("name"),
                "status": live.get("status"),
                "vcpus": live.get("cpus"),
                "ram_max_gb": live.get("mem_max_gb"),
                "ram_used_gb": live.get("mem_used_gb"),
            }
        )

    named = {}
    for row in vms:
        for eid in row.get("engine_ids") or []:
            named[str(eid)] = row
        if row["vmid"] == 101:
            named["wazuh_manager"] = row
        if row["vmid"] == 100:
            named["mssp_control"] = row

    return {
        "source": "proxmox_live",
        "hypervisor_node": raw.get("node"),
        "vms": vms,
        "extra_vms": extras[:20],
        "named": named,
        "note": (
            "Live from Proxmox (qm/pvesh): configured vCPU/RAM plus current use. "
            "Wazuh Manager = VM 101 wazuh-stack."
        ),
    }


def gather_proxmox_inventory(*, force: bool = False, allow_stale: bool = True) -> Dict[str, Any]:
    """Return enriched VM CPU/RAM inventory (cached ~90s, stale-while-revalidate)."""
    now = time.time()
    if not force and _cache["payload"] and (now - float(_cache["ts"])) < _CACHE_TTL:
        return dict(_cache["payload"])

    # Serve recent memory/file cache immediately; refresh in background.
    if not force and allow_stale:
        mem_age = now - float(_cache["ts"] or 0)
        if _cache["payload"] and mem_age < _STALE_TTL:
            _background_refresh()
            out = dict(_cache["payload"])
            out["source"] = f"{out.get('source') or 'proxmox'}_stale"
            return out
        file_raw = _read_file_cache(max_age=_STALE_TTL)
        if file_raw:
            enriched = _enrich(file_raw)
            enriched["source"] = "proxmox_file_cache"
            _cache["payload"] = enriched
            _cache["ts"] = now - (_CACHE_TTL + 1)  # mark soft-expired so next refresh sticks
            _background_refresh()
            return dict(enriched)

    raw, err = _ssh_pull()
    if raw is None:
        cached = _read_file_cache(max_age=_STALE_TTL)
        if cached:
            enriched = _enrich(cached)
            enriched["source"] = "proxmox_file_cache"
            enriched["warning"] = err
            _cache["ts"] = now
            _cache["payload"] = enriched
            return dict(enriched)
        return {
            "source": "unavailable",
            "error": err or "proxmox_unreachable",
            "vms": [],
            "named": {},
            "hint": (
                "Mount Proxmox SSH key at /run/secrets/proxmox_ssh_key and set "
                "PROXMOX_SSH_HOST (default 192.168.0.191)."
            ),
        }

    enriched = _enrich(raw)
    _cache["ts"] = now
    _cache["payload"] = enriched
    # Best-effort write host-visible cache when path is writable
    try:
        path = _cache_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(raw), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return dict(enriched)


def wants_proxmox(question: str) -> bool:
    q = (question or "").lower()
    keys = (
        "proxmox",
        "hypervisor",
        "vcpu",
        "vcpus",
        "v-cpu",
        "cpu core",
        "cores",
        "how much ram",
        "memory",
        "ram of",
        "ram on",
        "ram for",
        "vm 10",
        "vm10",
        "power state",
        "guest ram",
        "allocated ram",
        "configured ram",
    )
    if any(k in q for k in keys):
        return True
    # Engine + resource questions ("wazuh manager ram", "shuffle cpu")
    engines = (
        "wazuh",
        "shuffle",
        "thehive",
        "suricata",
        "greenbone",
        "mssp-control",
        "velociraptor",
        "misp",
    )
    resources = ("ram", "memory", "cpu", "vcpu", "core", "disk", "uptime")
    if any(e in q for e in engines) and any(r in q for r in resources):
        return True
    return False
