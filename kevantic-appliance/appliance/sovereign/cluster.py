"""Sovereign Edge logical active-active cluster (single-host lab + future multi-node).

No shared SAN: nodes replicate signed license artifacts through a local cluster bus.
"""

from __future__ import annotations

import json
import os
import secrets
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import error as urlerror
from urllib import request as urlrequest

CLUSTER_DIR_DEFAULT = "/var/lib/sovereign-cluster"
CLUSTER_META = "cluster.json"
SHARED_DIR = "shared"
INBOX_DIR = "inbox"
HEARTBEAT_STALE_SECONDS = 45
REPLICATED_ARTIFACTS = (
    "entitlements.json",
    "renewal-reminder.json",
    "license.jws",
)


def _cluster_dir() -> Path:
    return Path(os.environ.get("SOVEREIGN_CLUSTER_DIR", CLUSTER_DIR_DEFAULT))


def physical_state_dir() -> Path:
    for env_name in ("JUNEXIS_STATE_DIR", "KEVANTIC_STATE_DIR", "NIKTIAR_STATE_DIR"):
        env = os.environ.get(env_name, "").strip()
        if env:
            return Path(env)
    for candidate in (Path("/var/lib/junexis"), Path("/var/lib/kevantic"), Path("/var/lib/niktiar")):
        if candidate.is_dir():
            return candidate
    return Path("/var/lib/junexis")


def node_state_dir(node_id: str) -> Path:
    meta = _load_meta()
    if meta.get("topology") == "multihost" or os.environ.get("SOVEREIGN_CLUSTER_TOPOLOGY") == "multihost":
        return physical_state_dir()
    nid = node_id.strip().lower()
    env = os.environ.get(f"SOVEREIGN_NODE_{nid.upper()}_STATE_DIR", "").strip()
    if env:
        return Path(env)
    for candidate in (Path(f"/var/lib/niktiar-{nid}"), Path(f"/var/lib/junexis-{nid}")):
        if candidate.is_dir():
            return candidate
    return Path(f"/var/lib/niktiar-{nid}")


def node_api_port(node_id: str) -> int:
    meta = _load_meta()
    if meta.get("topology") == "multihost":
        info = (meta.get("nodes") or {}).get(node_id) or {}
        port = info.get("api_port")
        if port:
            return int(port)
    defaults = {"a": 8443, "b": 8444}
    env = os.environ.get(f"SOVEREIGN_NODE_{node_id.strip().upper()}_PORT", "").strip()
    if env.isdigit():
        return int(env)
    return defaults.get(node_id.strip().lower(), 8443)


def vip_host() -> str:
    return os.environ.get("SOVEREIGN_CLUSTER_VIP", "127.0.0.240")


def _meta_path() -> Path:
    return _cluster_dir() / CLUSTER_META


def _load_meta() -> Dict[str, Any]:
    path = _meta_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _save_meta(data: Dict[str, Any]) -> Dict[str, Any]:
    _cluster_dir().mkdir(parents=True, exist_ok=True)
    tmp = _meta_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(_meta_path())
    return data


def _peer_node_id(node_id: str, meta: Dict[str, Any]) -> str:
    for nid in (meta.get("nodes") or {}):
        if nid != node_id:
            return nid
    return "b" if node_id == "a" else "a"


def _join_token(meta: Dict[str, Any]) -> str:
    return str(meta.get("join_token") or "")


def _peer_request(
    meta: Dict[str, Any],
    *,
    peer_host: str,
    peer_port: int,
    path: str,
    method: str = "GET",
    body: Optional[bytes] = None,
) -> Dict[str, Any]:
    url = f"http://{peer_host}:{peer_port}{path}"
    headers = {"X-Sovereign-Join-Token": _join_token(meta)}
    if body is not None:
        headers["Content-Type"] = "application/octet-stream"
    req = urlrequest.Request(url, data=body, headers=headers, method=method)
    try:
        with urlrequest.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            if raw and raw[:1] in (b"{", b"["):
                return json.loads(raw.decode("utf-8"))
            return {"ok": True, "bytes": len(raw)}
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        return {"ok": False, "error": detail, "code": exc.code}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200]}


def bootstrap_multihost(
    *,
    node_id: str,
    local_host: str,
    peer_node_id: str,
    peer_host: str,
    api_port: int = 8443,
    peer_port: int = 8443,
    cluster_id: Optional[str] = None,
    join_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Pair two physical appliances as an active-active sovereign cluster."""
    token = join_token or secrets.token_urlsafe(24)
    state = physical_state_dir()
    state.mkdir(parents=True, exist_ok=True)
    meta = {
        "cluster_id": cluster_id or str(uuid.uuid4()),
        "topology": "multihost",
        "profile": "sovereign_edge_multihost_ha",
        "nodes": {
            node_id: {
                "host": local_host,
                "api_port": api_port,
                "state_dir": str(state),
                "role": "active",
            },
            peer_node_id: {
                "host": peer_host,
                "api_port": peer_port,
                "state_dir": str(state),
                "role": "active",
            },
        },
        "join_token": token,
        "generation": 0,
        "leader": node_id,
        "paired_at": int(time.time()),
        "vip": peer_host,
    }
    bus = _cluster_dir()
    for root in (bus / SHARED_DIR, bus / INBOX_DIR / node_id, bus / INBOX_DIR / peer_node_id):
        root.mkdir(parents=True, exist_ok=True)
    return _save_meta(meta)


def bootstrap_pair(
    *,
    node_ids: Tuple[str, str] = ("a", "b"),
    cluster_id: Optional[str] = None,
    join_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Initialize a 2-node logical cluster on one host."""
    # Logical pair replaces any prior multihost metadata on the shared cluster bus.
    meta_path = _meta_path()
    if meta_path.is_file():
        meta_path.unlink()
    a, b = node_ids
    token = join_token or secrets.token_urlsafe(24)
    meta = {
        "cluster_id": cluster_id or str(uuid.uuid4()),
        "topology": "logical_single_host",
        "profile": "sovereign_edge_logical_ha",
        "nodes": {
            a: {
                "state_dir": str(Path(f"/var/lib/niktiar-{a}")),
                "api_port": node_api_port(a),
                "role": "active",
            },
            b: {
                "state_dir": str(Path(f"/var/lib/niktiar-{b}")),
                "api_port": node_api_port(b),
                "role": "active",
            },
        },
        "join_token": token,
        "generation": 0,
        "leader": a,
        "paired_at": int(time.time()),
        "vip": vip_host(),
    }
    bus = _cluster_dir()
    for root in (bus / SHARED_DIR, bus / INBOX_DIR / a, bus / INBOX_DIR / b):
        root.mkdir(parents=True, exist_ok=True)
    for nid in node_ids:
        node_state_dir(nid).mkdir(parents=True, exist_ok=True)
    return _save_meta(meta)


def record_heartbeat(node_id: str) -> Dict[str, Any]:
    meta = _load_meta()
    if not meta:
        raise ValueError("cluster not paired")
    nodes = meta.setdefault("nodes", {})
    entry = nodes.setdefault(node_id, {})
    entry["last_seen_at"] = int(time.time())
    entry["state_dir"] = str(node_state_dir(node_id))
    entry["api_port"] = node_api_port(node_id)
    meta["leader"] = _elect_leader(meta)
    saved = _save_meta(meta)
    if meta.get("topology") == "multihost":
        _notify_peer_heartbeat(node_id, meta)
    return saved


def _notify_peer_heartbeat(node_id: str, meta: Dict[str, Any]) -> None:
    peer_id = _peer_node_id(node_id, meta)
    peer = (meta.get("nodes") or {}).get(peer_id) or {}
    host = str(peer.get("host") or "")
    port = int(peer.get("api_port") or 8443)
    if not host:
        return
    payload = json.dumps({"node_id": node_id, "last_seen_at": int(time.time())}).encode("utf-8")
    _peer_request(meta, peer_host=host, peer_port=port, path="/cluster/heartbeat", method="POST", body=payload)


def apply_remote_heartbeat(remote_node_id: str, last_seen_at: int) -> Dict[str, Any]:
    meta = _load_meta()
    if not meta:
        raise ValueError("cluster not paired")
    nodes = meta.setdefault("nodes", {})
    entry = nodes.setdefault(remote_node_id, {})
    entry["last_seen_at"] = int(last_seen_at)
    meta["leader"] = _elect_leader(meta)
    return _save_meta(meta)


def replicate_to_peer(node_id: str, *, artifacts: Optional[List[str]] = None) -> Dict[str, Any]:
    meta = _load_meta()
    if meta.get("topology") != "multihost":
        return {"ok": True, "skipped": True, "reason": "not_multihost"}
    peer_id = _peer_node_id(node_id, meta)
    peer = (meta.get("nodes") or {}).get(peer_id) or {}
    host = str(peer.get("host") or "")
    port = int(peer.get("api_port") or 8443)
    if not host:
        return {"ok": False, "error": "peer_host_missing"}
    names = list(artifacts or REPLICATED_ARTIFACTS)
    pushed: List[str] = []
    src_root = node_state_dir(node_id)
    for name in names:
        src = src_root / name
        if not src.is_file():
            continue
        result = _peer_request(
            meta,
            peer_host=host,
            peer_port=port,
            path=f"/cluster/artifact/{name}",
            method="POST",
            body=src.read_bytes(),
        )
        if not result.get("ok", True) and result.get("error"):
            return {"ok": False, "error": result.get("error"), "artifact": name}
        pushed.append(name)
    return {"ok": True, "pushed": pushed, "peer": f"{host}:{port}"}


def pull_from_peer(node_id: str, *, artifacts: Optional[List[str]] = None) -> Dict[str, Any]:
    meta = _load_meta()
    if meta.get("topology") != "multihost":
        return sync_from_shared(node_id, artifacts=artifacts)
    peer_id = _peer_node_id(node_id, meta)
    peer = (meta.get("nodes") or {}).get(peer_id) or {}
    host = str(peer.get("host") or "")
    port = int(peer.get("api_port") or 8443)
    if not host:
        raise ValueError("peer host missing")
    names = list(artifacts or REPLICATED_ARTIFACTS)
    dst_root = node_state_dir(node_id)
    dst_root.mkdir(parents=True, exist_ok=True)
    pulled: List[str] = []
    for name in names:
        data = _fetch_peer_artifact(meta, host, port, name)
        if not data:
            continue
        dest = dst_root / name
        tmp = dest.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(dest)
        pulled.append(name)
    return {"ok": True, "node_id": node_id, "pulled": pulled, "generation": int(meta.get("generation") or 0)}


def _fetch_peer_artifact(meta: Dict[str, Any], host: str, port: int, name: str) -> Optional[bytes]:
    url = f"http://{host}:{port}/cluster/artifact/{name}"
    req = urlrequest.Request(url, headers={"X-Sovereign-Join-Token": _join_token(meta)})
    try:
        with urlrequest.urlopen(req, timeout=10) as resp:
            return resp.read()
    except Exception:  # noqa: BLE001
        return None


def _elect_leader(meta: Dict[str, Any]) -> str:
    now = int(time.time())
    alive: List[Tuple[str, int]] = []
    for nid, info in (meta.get("nodes") or {}).items():
        seen = int(info.get("last_seen_at") or 0)
        if seen and (now - seen) <= HEARTBEAT_STALE_SECONDS:
            alive.append((nid, seen))
    if not alive:
        return str(meta.get("leader") or "a")
    alive.sort(key=lambda item: (-item[1], item[0]))
    return alive[0][0]


def publish_artifacts(node_id: str, *, artifacts: Optional[List[str]] = None) -> Dict[str, Any]:
    """Push local replicated artifacts to shared bus (writer must hold leadership)."""
    meta = _load_meta()
    if not meta:
        raise ValueError("cluster not paired")
    leader = _elect_leader(meta)
    if leader != node_id:
        raise ValueError(f"split-brain guard: node {node_id} is not leader ({leader})")

    names = list(artifacts or REPLICATED_ARTIFACTS)
    published: List[str] = []
    src_root = node_state_dir(node_id)
    shared = _cluster_dir() / SHARED_DIR
    shared.mkdir(parents=True, exist_ok=True)

    for name in names:
        src = src_root / name
        if not src.is_file():
            continue
        dest = shared / name
        tmp = dest.with_suffix(".tmp")
        tmp.write_bytes(src.read_bytes())
        tmp.replace(dest)
        published.append(name)

    meta["generation"] = int(meta.get("generation") or 0) + 1
    meta["last_publish_node"] = node_id
    meta["last_publish_at"] = int(time.time())
    meta["leader"] = leader
    _save_meta(meta)
    result: Dict[str, Any] = {
        "ok": True,
        "published": published,
        "generation": meta["generation"],
        "leader": leader,
    }
    if meta.get("topology") == "multihost":
        result["replicate"] = replicate_to_peer(node_id, artifacts=published or names)
    return result


def sync_from_shared(node_id: str, *, artifacts: Optional[List[str]] = None) -> Dict[str, Any]:
    """Pull shared bus artifacts into a node local state directory."""
    meta = _load_meta()
    if not meta:
        raise ValueError("cluster not paired")
    names = list(artifacts or REPLICATED_ARTIFACTS)
    dst_root = node_state_dir(node_id)
    dst_root.mkdir(parents=True, exist_ok=True)
    shared = _cluster_dir() / SHARED_DIR
    pulled: List[str] = []
    for name in names:
        src = shared / name
        if not src.is_file():
            continue
        dest = dst_root / name
        tmp = dest.with_suffix(".tmp")
        tmp.write_bytes(src.read_bytes())
        tmp.replace(dest)
        pulled.append(name)
    return {
        "ok": True,
        "node_id": node_id,
        "pulled": pulled,
        "generation": int(meta.get("generation") or 0),
    }


def active_api_endpoint(meta: Optional[Dict[str, Any]] = None) -> str:
    data = meta or _load_meta()
    leader = _elect_leader(data) if data else "a"
    if data.get("topology") == "multihost":
        info = (data.get("nodes") or {}).get(leader) or {}
        host = str(info.get("host") or "127.0.0.1")
        port = int(info.get("api_port") or 8443)
        return f"http://{host}:{port}"
    port = node_api_port(leader)
    return f"http://127.0.0.1:{port}"


def simulate_stale_node(node_id: str, *, stale_seconds: int = HEARTBEAT_STALE_SECONDS + 30) -> Dict[str, Any]:
    """Lab-only: age out a node heartbeat to exercise leader failover."""
    meta = _load_meta()
    if not meta:
        raise ValueError("cluster not paired")
    nodes = meta.setdefault("nodes", {})
    entry = nodes.setdefault(node_id, {})
    entry["last_seen_at"] = int(time.time()) - max(stale_seconds, HEARTBEAT_STALE_SECONDS + 1)
    meta["leader"] = _elect_leader(meta)
    _save_meta(meta)
    return {"ok": True, "node_id": node_id, "leader": meta["leader"], "simulated_stale": True}


def cluster_status(node_id: Optional[str] = None) -> Dict[str, Any]:
    meta = _load_meta()
    if not meta:
        return {"paired": False, "ok": False}
    leader = _elect_leader(meta)
    now = int(time.time())
    nodes_out: Dict[str, Any] = {}
    for nid, info in (meta.get("nodes") or {}).items():
        seen = int(info.get("last_seen_at") or 0)
        nodes_out[nid] = {
            "host": info.get("host"),
            "api_port": info.get("api_port") or node_api_port(nid),
            "state_dir": info.get("state_dir") or str(node_state_dir(nid)),
            "last_seen_at": seen or None,
            "stale": bool(seen and (now - seen) > HEARTBEAT_STALE_SECONDS),
            "healthy": bool(seen and (now - seen) <= HEARTBEAT_STALE_SECONDS),
        }
    return {
        "paired": True,
        "ok": True,
        "cluster_id": meta.get("cluster_id"),
        "topology": meta.get("topology"),
        "generation": meta.get("generation"),
        "leader": leader,
        "vip": meta.get("vip") or vip_host(),
        "active_endpoint": active_api_endpoint(meta),
        "node_id": node_id,
        "nodes": nodes_out,
    }
