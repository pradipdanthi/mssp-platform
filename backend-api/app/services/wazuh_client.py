"""Wazuh Manager API client (agent groups). Secrets via env/files only."""

from __future__ import annotations

import json
import logging
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple

from app.core.secrets import read_secret

logger = logging.getLogger(__name__)


class WazuhClientError(Exception):
    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


def _base_url() -> str:
    from app.core.config import get_infra_settings
    return get_infra_settings().wazuh_api_url.rstrip("/")


def _credentials() -> Tuple[str, str]:
    user = read_secret(
        "WAZUH_API_USER",
        "/run/secrets/wazuh_api_user",
        "/opt/mssp-control/.secrets/wazuh_api_user",
    )
    password = read_secret(
        "WAZUH_API_PASSWORD",
        "/run/secrets/wazuh_api_password",
        "/opt/mssp-control/.secrets/wazuh_api_password",
    )
    if not user or not password:
        raise WazuhClientError(
            "Wazuh API credentials missing (WAZUH_API_USER / WAZUH_API_PASSWORD files)"
        )
    return user, password


def _ssl_context() -> ssl.SSLContext:
    # Lab managers often use self-signed certs.
    verify = (__import__("os").getenv("WAZUH_API_VERIFY_TLS", "false") or "false").lower()
    if verify in ("1", "true", "yes"):
        return ssl.create_default_context()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _request(
    method: str,
    path: str,
    *,
    token: Optional[str] = None,
    basic: Optional[Tuple[str, str]] = None,
    body: Optional[Dict[str, Any]] = None,
    timeout: int = 20,
) -> Dict[str, Any]:
    url = _base_url() + path
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    if basic and not token:
        import base64

        raw = base64.b64encode(f"{basic[0]}:{basic[1]}".encode()).decode()
        req.add_header("Authorization", f"Basic {raw}")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise WazuhClientError(f"Wazuh API HTTP {exc.code}: {detail}", status=exc.code) from exc
    except urllib.error.URLError as exc:
        raise WazuhClientError(f"Wazuh API unreachable: {exc.reason}") from exc


def authenticate() -> str:
    user, password = _credentials()
    payload = _request(
        "POST",
        "/security/user/authenticate",
        basic=(user, password),
    )
    token = (payload.get("data") or {}).get("token")
    if not token:
        raise WazuhClientError("Wazuh authenticate returned no token")
    return str(token)


def ensure_agent_group(group_id: str) -> Dict[str, Any]:
    """Create agent group if missing. Idempotent.

    Wazuh 4.14+ expects POST /groups with JSON body {"group_id": "..."}.
    Query-param group_id is rejected as "Extra query parameter(s)".
    """
    token = authenticate()
    gid = group_id.strip()
    if not gid:
        raise WazuhClientError("Empty Wazuh group id")
    # List existing
    listed = _request("GET", f"/groups?groups_list={urllib.parse.quote(gid)}", token=token)
    affected = (listed.get("data") or {}).get("affected_items") or []
    if any(str(item.get("name") or "") == gid for item in affected):
        return {"created": False, "group_id": gid, "detail": "exists"}
    # Create (Wazuh Manager API 4.14.x)
    try:
        _request("POST", "/groups", token=token, body={"group_id": gid})
        return {"created": True, "group_id": gid, "detail": "created"}
    except WazuhClientError as exc:
        detail = str(exc).lower()
        # Real idempotent conflict only — do not treat unrelated 400s as success
        if exc.status in (409,) or "already exists" in detail or "exist" in detail:
            return {"created": False, "group_id": gid, "detail": "exists_or_conflict"}
        raise


def get_agent_groups(agent_id: str) -> list[str]:
    """Return agent group names from Manager API (empty list if unknown)."""
    aid = (agent_id or "").strip()
    if not aid:
        return []
    token = authenticate()
    listed = _request(
        "GET",
        f"/agents?agents_list={urllib.parse.quote(aid)}&select=id,name,group",
        token=token,
    )
    items = (listed.get("data") or {}).get("affected_items") or []
    if not items:
        return []
    groups = items[0].get("group") or []
    if isinstance(groups, str):
        return [groups] if groups else []
    return [str(g) for g in groups if g]


def assign_agent_to_group(agent_id: str, group_id: str, *, force: bool = True) -> Dict[str, Any]:
    """Assign an agent to a manager group (idempotent best-effort)."""
    aid = (agent_id or "").strip()
    gid = (group_id or "").strip()
    if not aid or not gid:
        raise WazuhClientError("agent_id and group_id are required")
    ensure_agent_group(gid)
    token = authenticate()
    # Wazuh 4.14: PUT /agents/{id}/group/{group_id} (no force query).
    path = f"/agents/{urllib.parse.quote(aid)}/group/{urllib.parse.quote(gid)}"
    try:
        return _request("PUT", path, token=token)
    except WazuhClientError as exc:
        if exc.status in (400, 404, 405, 409):
            # Already in group or alternate endpoint shapes.
            groups = get_agent_groups(aid)
            if gid in groups:
                return {"data": {"affected_items": [{"id": aid, "group": groups}]}, "message": "already_in_group"}
            if force:
                alt = f"/agents/{urllib.parse.quote(aid)}/group/{urllib.parse.quote(gid)}"
                try:
                    return _request("PUT", alt, token=token)
                except WazuhClientError:
                    pass
        raise


def credentials_configured() -> bool:
    try:
        _credentials()
        return True
    except WazuhClientError:
        return False


def get_agent_os(agent_id: str) -> str:
    """Return 'windows' or 'linux' (default) for the agent's OS platform."""
    aid = (agent_id or "").strip()
    if not aid:
        return "linux"
    try:
        token = authenticate()
        result = _request(
            "GET",
            f"/agents?agents_list={urllib.parse.quote(aid)}&select=os.platform",
            token=token,
        )
        items = (result.get("data") or {}).get("affected_items") or []
        if items:
            platform = str((items[0].get("os") or {}).get("platform") or "").lower()
            if "windows" in platform:
                return "windows"
    except Exception:
        pass
    return "linux"


def get_agent_status(agent_id: str) -> Dict[str, Any]:
    """Return manager view of agent id/name/status/lastKeepAlive for verification."""
    aid = (agent_id or "").strip()
    if not aid:
        raise WazuhClientError("agent_id is required")
    token = authenticate()
    listed = _request(
        "GET",
        f"/agents?agents_list={urllib.parse.quote(aid)}&select=id,name,status,lastKeepAlive,ip",
        token=token,
    )
    items = (listed.get("data") or {}).get("affected_items") or []
    if not items:
        raise WazuhClientError(f"Agent {aid} not found on manager", status=404)
    item = items[0]
    return {
        "id": str(item.get("id") or aid),
        "name": item.get("name"),
        "status": item.get("status"),
        "last_keep_alive": item.get("lastKeepAlive"),
        "ip": item.get("ip"),
    }


def list_agents_in_group(group_id: str, *, limit: int = 500) -> list[Dict[str, Any]]:
    """Return agents assigned to a manager group (excludes manager id 000)."""
    gid = (group_id or "").strip()
    if not gid:
        return []
    token = authenticate()
    qlimit = max(1, min(int(limit), 1000))
    listed = _request(
        "GET",
        (
            f"/agents?group={urllib.parse.quote(gid)}"
            f"&select=id,name,ip,status,group,os.name,os.platform,dateAdd,lastKeepAlive"
            f"&limit={qlimit}"
        ),
        token=token,
    )
    items = (listed.get("data") or {}).get("affected_items") or []
    out: list[Dict[str, Any]] = []
    for item in items:
        aid = str(item.get("id") or "").strip()
        if not aid or aid == "000":
            continue
        os_info = item.get("os") or {}
        out.append(
            {
                "id": aid,
                "name": item.get("name"),
                "ip": item.get("ip"),
                "status": item.get("status"),
                "group": item.get("group") or [],
                "os_name": os_info.get("name"),
                "os_platform": os_info.get("platform"),
                "date_add": item.get("dateAdd"),
                "last_keep_alive": item.get("lastKeepAlive"),
            }
        )
    return out


def run_active_response(
    *,
    agent_id: str,
    command: str,
    arguments: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """
    Dispatch Wazuh active response to one agent (Wazuh 4.14 API).

    Manager expects API-triggered commands with a leading ``!``
    (e.g. ``!mssp-isolate-host``). ``custom`` is not accepted by this API version.
    """
    aid = (agent_id or "").strip()
    if not aid:
        raise WazuhClientError("agent_id is required for active response")
    cmd = (command or "").strip()
    if not cmd:
        raise WazuhClientError("active response command is required")
    if not cmd.startswith("!"):
        cmd = f"!{cmd}"
    token = authenticate()
    body: Dict[str, Any] = {
        "command": cmd,
        "arguments": [str(a) for a in (arguments or [])],
    }
    path = f"/active-response?agents_list={urllib.parse.quote(aid)}"
    result = _request("PUT", path, token=token, body=body)
    data = result.get("data") or {}
    if int(data.get("total_failed_items") or 0) > 0 or int(result.get("error") or 0) != 0:
        failed = data.get("failed_items") or []
        detail = ""
        if failed and isinstance(failed[0], dict):
            err = (failed[0].get("error") or {})
            detail = str(err.get("message") or failed[0])[:300]
        raise WazuhClientError(
            detail or f"Active response failed for agent {aid} command {cmd}",
            status=400,
        )
    return result


def run_custom_active_response(
    *,
    agent_id: str,
    command_line: str,
    arguments: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """Dispatch a named AR executable (same as run_active_response)."""
    return run_active_response(
        agent_id=agent_id,
        command=command_line,
        arguments=arguments,
    )
