"""Register / heartbeat / job execution against control-plane KB-016 APIs."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from kevantic_cli import state


def _secrets_dir() -> Path:
    d = state.state_root() / "secrets"
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    return d


def api_key_path() -> Path:
    return _secrets_dir() / "appliance_api_key"


def save_api_key(raw: str) -> None:
    p = api_key_path()
    p.write_text(raw.strip() + "\n", encoding="utf-8")
    os.chmod(p, 0o600)


def load_api_key() -> str:
    p = api_key_path()
    if not p.is_file():
        raise FileNotFoundError("appliance API key not found; run kevantic-cli register first")
    return p.read_text(encoding="utf-8").strip()


def _control_plane_base(app: dict[str, Any]) -> str:
    base = (
        app.get("control_plane")
        or os.environ.get("KEVANTIC_CONTROL_PLANE")
        or state.default_control_plane()
    ).rstrip("/")
    if not base:
        raise ValueError("control_plane URL missing; pass --control-plane or run setup first")
    # Allow http://192.168.0.224:8000 (Appliance Mgmt) or https://soc.kevantic.com
    if base.endswith("/api"):
        base = base[:-4]
    return base


def _guess_local_ip() -> Optional[str]:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def _http_json(
    method: str,
    url: str,
    *,
    body: Optional[dict] = None,
    headers: Optional[dict] = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    data = None
    hdrs = {"Accept": "application/json", "User-Agent": "kevantic-cli/register"}
    if headers:
        hdrs.update(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"network error: {exc}") from exc


def _persist_registration_locally(
    *,
    raw_key: str,
    app: dict[str, Any],
    base: str,
) -> None:
    """Write API key + state + appliance.env. Raises OSError/PermissionError on failure."""
    save_api_key(raw_key)
    state.save_appliance_state(app)
    env_path = state.config_root() / "appliance.env"
    state.config_root().mkdir(parents=True, exist_ok=True)
    env_path.write_text(
        (
            f"KEVANTIC_APPLIANCE_ID={app['appliance_id']}\n"
            f"KEVANTIC_CONTROL_PLANE={base}\n"
            f"KEVANTIC_TELEMETRY_URL={base}/api/v1/telemetry/ingest\n"
            f"KEVANTIC_STATE_DIR={state.state_root()}\n"
        ),
        encoding="utf-8",
    )
    os.chmod(env_path, 0o640)


def _abort_registration_on_control_plane(
    *,
    base: str,
    appliance_id: str,
    raw_key: str,
) -> None:
    """Best-effort: retire control-plane row if local persist failed after register."""
    url = f"{base.rstrip('/')}/appliance/registration/abort"
    req = urllib.request.Request(
        url,
        data=b"{}",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "kevantic-cli/register-abort",
            "X-Appliance-ID": appliance_id,
            "X-Appliance-API-Key": raw_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            resp.read()
    except Exception as exc:  # noqa: BLE001 — surface as secondary note only
        raise RuntimeError(f"control-plane abort also failed: {exc}") from exc


def register(
    *,
    activation_token: str,
    control_plane: Optional[str] = None,
    appliance_name: Optional[str] = None,
    local_ip: Optional[str] = None,
) -> dict[str, Any]:
    state.ensure_dirs()
    app = state.load_appliance_state()
    if control_plane:
        app["control_plane"] = control_plane.rstrip("/")
    name = (appliance_name or app.get("appliance_name") or "kevantic-appliance").strip()
    app["appliance_name"] = name
    uuid = app.get("appliance_uuid") or str(uuid4())
    app["appliance_uuid"] = uuid
    ip = local_ip or _guess_local_ip()
    base = _control_plane_base(app)
    url = f"{base}/appliance/register"
    resp = _http_json(
        "POST",
        url,
        body={
            "activation_token": activation_token,
            "appliance_name": name,
            "appliance_uuid": uuid,
            "local_ip": ip,
            "agent_version": "0.1.0-dev",
            "config_version": "track1",
        },
    )
    raw_key = resp.get("appliance_api_key")
    if not raw_key:
        raise RuntimeError("register response missing appliance_api_key")
    appliance_id = resp.get("appliance_id")
    if not appliance_id:
        raise RuntimeError("register response missing appliance_id")

    app["registration"] = "registered"
    app["appliance_id"] = appliance_id
    app["tenant_id"] = resp.get("tenant_id")
    app["tenant_short_code"] = resp.get("tenant_short_code")
    app["site_name"] = resp.get("site_name") or app.get("site_name") or ""
    app["api_key_hint"] = resp.get("api_key_hint")
    app["local_ip"] = ip

    try:
        _persist_registration_locally(raw_key=raw_key, app=app, base=base)
    except OSError as exc:
        abort_note = ""
        try:
            _abort_registration_on_control_plane(
                base=base, appliance_id=str(appliance_id), raw_key=raw_key
            )
            abort_note = (
                " Control-plane registration was rolled back (appliance retired)."
                " Mint a new activation token before retrying."
            )
        except Exception as abort_exc:  # noqa: BLE001
            abort_note = (
                f" CRITICAL: control-plane row may still show in Admin"
                f" (abort failed: {abort_exc}). Retire it manually in Admin → Appliances."
            )
        raise RuntimeError(
            f"Registered on control plane but failed to store credentials locally "
            f"({exc}).{abort_note}"
        ) from exc

    post = _post_register_local_manager(app)

    return {
        "ok": True,
        "appliance_id": app["appliance_id"],
        "tenant_short_code": app.get("tenant_short_code"),
        "api_key_hint": app.get("api_key_hint"),
        "local_ip": ip,
        "control_plane": base,
        "local_manager": post,
        "message": "Registered. API key stored under /var/lib/kevantic/secrets/ (mode 0600).",
    }


def _tenant_agent_group(short_code: Optional[str]) -> str:
    code = (short_code or "UNKNOWN").strip().upper().replace("-", "_")
    return f"tenant_{code}"


def _post_register_local_manager(app: dict[str, Any]) -> dict[str, Any]:
    """
    After successful register: enable local Wazuh Manager and ensure tenant agent group.
    Best-effort — registration itself already succeeded.
    """
    result: dict[str, Any] = {
        "wazuh_manager": "skipped",
        "agent_group": None,
        "group_created": False,
        "errors": [],
    }
    group = _tenant_agent_group(app.get("tenant_short_code"))
    result["agent_group"] = group

    try:
        subprocess.run(
            ["systemctl", "enable", "--now", "wazuh-manager"],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        # Wait briefly for authd/remoted
        import time

        time.sleep(3)
        st = subprocess.run(
            ["systemctl", "is-active", "wazuh-manager"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        result["wazuh_manager"] = (st.stdout or "").strip() or "unknown"
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"enable_manager: {exc}")
        result["wazuh_manager"] = "error"

    # Create tenant group (ignore if exists)
    try:
        list_out = subprocess.run(
            ["/var/ossec/bin/agent_groups", "-l"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if group not in (list_out.stdout or ""):
            subprocess.run(
                ["/var/ossec/bin/agent_groups", "-a", "-g", group, "-q"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            result["group_created"] = True
        else:
            result["group_created"] = False
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"agent_group: {exc}")

    # Persist expected group for operators
    try:
        state.ensure_dirs()
        (state.state_root() / "wazuh_agent_group").write_text(group + "\n", encoding="utf-8")
    except Exception:
        pass

    return result


def _read_enabled_services() -> list[str]:
    ents = state.load_entitlements()
    svcs = ents.get("service_ids") or []
    return [str(s) for s in svcs]


def _collect_agent_inventory() -> list[dict[str, Any]]:
    """Best-effort local Manager agent list via wazuh-control / API if present."""
    # Prefer a tiny helper script if present; else empty (heartbeat still works).
    helper = Path("/usr/bin/kevantic-list-local-agents")
    if helper.is_file():
        try:
            out = subprocess.check_output([str(helper)], timeout=20, text=True)
            data = json.loads(out)
            if isinstance(data, list):
                return data
        except Exception:
            pass
    # Optional: Wazuh API on localhost (default appliance Manager)
    user = os.environ.get("WAZUH_API_USER", "wazuh-wui")
    password = os.environ.get("WAZUH_API_PASSWORD", "")
    if not password:
        return []
    try:
        # Token
        import base64

        auth = base64.b64encode(f"{user}:{password}".encode()).decode()
        token_resp = _http_json(
            "GET",
            "https://127.0.0.1:55000/security/user/authenticate",
            headers={"Authorization": f"Basic {auth}"},
            timeout=10,
        )
        token = (token_resp.get("data") or {}).get("token")
        if not token:
            return []
        agents_resp = _http_json(
            "GET",
            "https://127.0.0.1:55000/agents?limit=500&select=id,name,status,ip,os.name,os.platform,lastKeepAlive",
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
        items = ((agents_resp.get("data") or {}).get("affected_items")) or []
        out = []
        for a in items:
            if str(a.get("id")) == "000":
                continue
            os_info = a.get("os") or {}
            out.append(
                {
                    "id": str(a.get("id")),
                    "name": a.get("name"),
                    "status": a.get("status"),
                    "ip": a.get("ip"),
                    "os_name": os_info.get("name"),
                    "os_platform": os_info.get("platform"),
                    "last_keep_alive": a.get("lastKeepAlive"),
                }
            )
        return out
    except Exception:
        return []


def _run_local_ar(job: dict[str, Any]) -> tuple[bool, str]:
    """Execute Active Response against local Manager for a pulled job."""
    payload = job.get("payload") or {}
    agent_id = str(payload.get("agent_id") or "")
    command = str(payload.get("ar_command") or "")
    arguments = payload.get("arguments") or []
    if not agent_id or not command:
        return False, "missing agent_id or ar_command"
    # Use wazuh API if creds present
    user = os.environ.get("WAZUH_API_USER", "wazuh-wui")
    password = os.environ.get("WAZUH_API_PASSWORD", "")
    if not password:
        return False, "WAZUH_API_PASSWORD not set on appliance"
    try:
        import base64

        auth = base64.b64encode(f"{user}:{password}".encode()).decode()
        token_resp = _http_json(
            "GET",
            "https://127.0.0.1:55000/security/user/authenticate",
            headers={"Authorization": f"Basic {auth}"},
            timeout=10,
        )
        token = (token_resp.get("data") or {}).get("token")
        if not token:
            return False, "local Manager auth failed"
        cmd = command if command.startswith("!") else f"!{command}"
        _http_json(
            "PUT",
            f"https://127.0.0.1:55000/active-response?agents_list={agent_id}",
            body={"command": cmd, "arguments": [str(a) for a in arguments]},
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        return True, f"AR {command} dispatched to agent {agent_id}"
    except Exception as exc:
        return False, str(exc)[:300]


def _dispatch_job(job: dict[str, Any]) -> tuple[bool, str]:
    """Route pending control-plane jobs to the correct local handler."""
    from kevantic_cli import network as network_ops

    job_type = str(job.get("job_type") or "").strip()
    payload = job.get("payload") or {}
    if job_type == "set_agent_cidrs":
        cidrs = payload.get("cidrs") or []
        if not isinstance(cidrs, list):
            return False, "payload.cidrs must be a list"
        try:
            result = network_ops.apply_agent_cidrs(cidrs)
            return True, json.dumps(result)[:500]
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)[:300]
    if job_type in ("enable_local_manager", "ensure_local_manager"):
        app = state.load_appliance_state()
        post = _post_register_local_manager(app)
        ok = post.get("wazuh_manager") == "active"
        return ok, json.dumps(post)[:500]
    # Default: Active Response / isolate-style jobs
    if payload.get("ar_command") or payload.get("agent_id"):
        return _run_local_ar(job)
    return False, f"unsupported job_type: {job_type or 'missing'}"


def heartbeat(*, include_inventory: bool = True) -> dict[str, Any]:
    app = state.load_appliance_state()
    appliance_id = app.get("appliance_id")
    if not appliance_id:
        raise RuntimeError("not registered; run kevantic-cli register first")
    api_key = load_api_key()
    base = _control_plane_base(app)
    body: dict[str, Any] = {
        "health_status": "healthy",
        "local_ip": app.get("local_ip") or _guess_local_ip(),
        "agent_version": "0.1.0-dev",
        "enabled_services": _read_enabled_services(),
        "health_snapshot": {
            "source": "kevantic-cli",
            "agent_source_cidrs": __import__(
                "kevantic_cli.network", fromlist=["load_agent_cidrs"]
            ).load_agent_cidrs(),
        },
    }
    if include_inventory:
        body["agent_inventory"] = _collect_agent_inventory()
    url = f"{base}/appliance/heartbeat"
    resp = _http_json(
        "POST",
        url,
        body=body,
        headers={
            "X-Appliance-ID": str(appliance_id),
            "X-Appliance-API-Key": api_key,
        },
    )
    jobs = resp.get("pending_jobs") or []
    job_results = []
    for job in jobs:
        ok, msg = _dispatch_job(job)
        job_id = job.get("id")
        if job_id:
            try:
                ack = _http_json(
                    "POST",
                    f"{base}/appliance/jobs/{job_id}/ack",
                    body={"success": ok, "message": msg, "result": {"detail": msg}},
                    headers={
                        "X-Appliance-ID": str(appliance_id),
                        "X-Appliance-API-Key": api_key,
                    },
                )
                job_results.append({"job_id": job_id, "ack": ack, "ok": ok, "message": msg})
            except Exception as exc:
                job_results.append({"job_id": job_id, "ok": ok, "message": msg, "ack_error": str(exc)})
    # Flush telemetry buffer best-effort
    try:
        from appliance.telemetry.forwarder import TelemetryForwarder

        os.environ.setdefault("KEVANTIC_APPLIANCE_ID", str(appliance_id))
        os.environ.setdefault("KEVANTIC_APPLIANCE_API_KEY", api_key)
        os.environ.setdefault("KEVANTIC_TELEMETRY_URL", f"{base}/api/v1/telemetry/ingest")
        TelemetryForwarder().flush_buffer(max_items=50)
    except Exception:
        pass
    return {
        "ok": True,
        "heartbeat": {
            "appliance_id": resp.get("appliance_id"),
            "status": resp.get("status"),
            "heartbeat_at": resp.get("heartbeat_at"),
            "agent_inventory_sync": resp.get("agent_inventory_sync"),
        },
        "jobs_processed": job_results,
        "jobs_pulled": len(jobs),
    }
