"""Register / heartbeat / job execution against control-plane KB-016 APIs."""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

try:
    from kevantic_cli import state
except ImportError:  # branded junexis image
    from junexis_cli import state

logger = logging.getLogger(__name__)


def _cli_submodule(name: str):
    """Load kevantic_cli.<name> or junexis_cli.<name> depending on image brand."""
    last: Exception | None = None
    for pkg in ("kevantic_cli", "junexis_cli"):
        try:
            return __import__(f"{pkg}.{name}", fromlist=["*"])
        except ImportError as exc:
            last = exc
    raise ImportError(f"{name} not found in kevantic_cli or junexis_cli") from last

_AGENT_INVENTORY_HELPERS = (
    "/usr/bin/kevantic-list-local-agents",
    "/usr/bin/junexis-list-local-agents",
)


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


def _read_secret_line(*paths: str) -> str:
    for raw in paths:
        try:
            text = Path(raw).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            return text.splitlines()[0].strip()
    return ""


def _wazuh_api_credential_candidates() -> list[tuple[str, str]]:
    """Local Manager API users. Env/files first; factory package defaults last."""
    user = (
        os.environ.get("WAZUH_API_USER", "").strip()
        or _read_secret_line(
            "/var/lib/junexis/secrets/wazuh_api_user",
            "/var/lib/kevantic/secrets/wazuh_api_user",
        )
        or "wazuh-wui"
    )
    password = os.environ.get("WAZUH_API_PASSWORD", "").strip() or _read_secret_line(
        "/var/lib/junexis/secrets/wazuh_api_password",
        "/var/lib/kevantic/secrets/wazuh_api_password",
    )
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    if password:
        pairs.append((user, password))
        seen.add((user, password))
    for cand in (("wazuh-wui", "wazuh-wui"), ("wazuh", "wazuh")):
        if cand not in seen:
            pairs.append(cand)
            seen.add(cand)
    return pairs


def _wazuh_local_json(
    method: str,
    path: str,
    *,
    headers: Optional[dict] = None,
    body: Optional[dict] = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Call localhost Wazuh API (self-signed TLS)."""
    import ssl

    url = f"https://127.0.0.1:55000{path}"
    hdrs = {"Accept": "application/json", "User-Agent": "kevantic-cli/local-wazuh"}
    if headers:
        hdrs.update(headers)
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"Wazuh API HTTP {exc.code}: {detail}") from exc


def _authenticate_local_wazuh() -> str:
    import base64

    last_err = "local Manager auth failed"
    for user, password in _wazuh_api_credential_candidates():
        auth = base64.b64encode(f"{user}:{password}".encode()).decode()
        try:
            token_resp = _wazuh_local_json(
                "GET",
                "/security/user/authenticate",
                headers={"Authorization": f"Basic {auth}"},
                timeout=10,
            )
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)[:200]
            continue
        token = (token_resp.get("data") or {}).get("token")
        if token:
            return str(token)
    raise RuntimeError(last_err)


_EDR_AR_COMMAND_BLOCK = """
  <!-- MSSP EDR Active Response (appliance-local Manager) -->
  <command>
    <name>mssp-isolate-host</name>
    <executable>mssp-isolate-host</executable>
    <timeout_allowed>no</timeout_allowed>
  </command>
  <command>
    <name>mssp-kill-process</name>
    <executable>mssp-kill-process</executable>
    <timeout_allowed>no</timeout_allowed>
  </command>
  <command>
    <name>mssp-block-hash</name>
    <executable>mssp-block-hash</executable>
    <timeout_allowed>no</timeout_allowed>
  </command>
  <command>
    <name>mssp-isolate-host.cmd</name>
    <executable>mssp-isolate-host.cmd</executable>
    <timeout_allowed>no</timeout_allowed>
  </command>
  <command>
    <name>mssp-kill-process.cmd</name>
    <executable>mssp-kill-process.cmd</executable>
    <timeout_allowed>no</timeout_allowed>
  </command>
  <command>
    <name>mssp-block-hash.cmd</name>
    <executable>mssp-block-hash.cmd</executable>
    <timeout_allowed>no</timeout_allowed>
  </command>
"""


def _chown_wazuh(path: Path) -> None:
    try:
        import grp
        import pwd

        os.chown(path, pwd.getpwnam("wazuh").pw_uid, grp.getgrnam("wazuh").gr_gid)
    except Exception:
        pass


def _publish_windows_edr_ar_shared() -> None:
    """Push isolate scripts + sync helper into Manager shared groups."""
    src_dirs = (
        Path("/var/lib/junexis/edr-ar/windows"),
        Path("/var/lib/kevantic/edr-ar/windows"),
        Path("/opt/junexis/edr-ar/windows"),
        Path("/opt/kevantic/edr-ar/windows"),
    )
    src = next((d for d in src_dirs if (d / "mssp-isolate-host.ps1").is_file()), None)
    shared_root = Path("/var/ossec/etc/shared")
    if not shared_root.is_dir():
        return
    files = (
        "mssp-isolate-host.cmd",
        "mssp-isolate-host.ps1",
        "mssp-kill-process.cmd",
        "mssp-kill-process.ps1",
        "mssp-block-hash.cmd",
        "mssp-block-hash.ps1",
        "Watch-MsspQuarantine.ps1",
        "Sync-MsspEdrAr.ps1",
    )
    agent_conf = """<agent_config os="windows">
  <wodle name="command">
    <disabled>no</disabled>
    <tag>mssp-edr-ar-sync</tag>
    <interval>1m</interval>
    <run_on_start>yes</run_on_start>
    <timeout>60</timeout>
    <ignore_output>yes</ignore_output>
    <command>powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\\Program Files (x86)\\ossec-agent\\shared\\Sync-MsspEdrAr.ps1"</command>
  </wodle>
</agent_config>
"""
    for group_dir in shared_root.iterdir():
        if not group_dir.is_dir() or group_dir.name in ("agent-template",):
            continue
        if src:
            for name in files:
                p = src / name
                if not p.is_file():
                    continue
                dest = group_dir / name
                try:
                    dest.write_bytes(p.read_bytes())
                except OSError as exc:
                    # channeld ProtectSystem=strict makes /var/ossec EROFS.
                    # Isolate must still dispatch; skip this group file.
                    logger.warning("skip shared publish %s: %s", dest, exc)
                    continue
                try:
                    dest.chmod(0o640)
                except OSError:
                    pass
                _chown_wazuh(dest)
        conf_path = group_dir / "agent.conf"
        try:
            current = conf_path.read_text(encoding="utf-8") if conf_path.is_file() else ""
        except OSError:
            continue
        if "mssp-edr-ar-sync" not in current:
            try:
                new = (
                    current.rstrip() + "\n" + agent_conf
                    if current.strip()
                    else agent_conf
                )
                conf_path.write_text(new, encoding="utf-8")
            except OSError as exc:
                logger.warning("skip shared agent.conf %s: %s", conf_path, exc)
                continue
            try:
                conf_path.chmod(0o660)
            except OSError:
                pass
            _chown_wazuh(conf_path)


_LINUX_EXEC_AGENT_CONF = """<agent_config os="linux">
  <!-- mssp-linux-exec-localfile -->
  <localfile>
    <log_format>audit</log_format>
    <location>/var/log/audit/audit.log</location>
  </localfile>
  <wodle name="command">
    <disabled>no</disabled>
    <tag>mssp-linux-exec-sync</tag>
    <interval>60m</interval>
    <run_on_start>yes</run_on_start>
    <timeout>120</timeout>
    <ignore_output>yes</ignore_output>
    <command>bash /var/ossec/etc/shared/install-mssp-linux-telemetry.sh</command>
  </wodle>
</agent_config>
"""

_LINUX_EXEC_RULES_SRC = (
    Path("/var/lib/kevantic/edr-ar/linux/mssp_linux_exec_rules.xml"),
    Path("/var/lib/junexis/edr-ar/linux/mssp_linux_exec_rules.xml"),
    Path("/opt/kevantic/edr-ar/linux/mssp_linux_exec_rules.xml"),
    Path("/opt/junexis/edr-ar/linux/mssp_linux_exec_rules.xml"),
    Path("/tmp/mssp_linux_exec_rules.xml"),
)

_LINUX_TELEMETRY_SRC = (
    Path("/var/lib/kevantic/edr-ar/linux/install-mssp-linux-telemetry.sh"),
    Path("/var/lib/junexis/edr-ar/linux/install-mssp-linux-telemetry.sh"),
    Path("/opt/kevantic/edr-ar/linux/install-mssp-linux-telemetry.sh"),
    Path("/opt/junexis/edr-ar/linux/install-mssp-linux-telemetry.sh"),
    Path("/tmp/install-mssp-linux-telemetry.sh"),
)

_LINUX_EXEC_RULES_DST = Path("/var/ossec/etc/rules/mssp_linux_exec_rules.xml")


def _first_existing_file(paths) -> Optional[Path]:
    for path in paths:
        if path.is_file():
            return path
    return None


def _publish_linux_midlayer_shared() -> None:
    """Drop Linux execve helper into Manager shared groups; APPEND agent.conf."""
    shared_root = Path("/var/ossec/etc/shared")
    helper = _first_existing_file(_LINUX_TELEMETRY_SRC)
    rules_src = _first_existing_file(_LINUX_EXEC_RULES_SRC)
    if rules_src is not None:
        try:
            _LINUX_EXEC_RULES_DST.parent.mkdir(parents=True, exist_ok=True)
            current = (
                _LINUX_EXEC_RULES_DST.read_bytes()
                if _LINUX_EXEC_RULES_DST.is_file()
                else b""
            )
            payload = rules_src.read_bytes()
            if current != payload:
                _LINUX_EXEC_RULES_DST.write_bytes(payload)
                try:
                    _LINUX_EXEC_RULES_DST.chmod(0o640)
                except OSError:
                    pass
                _chown_wazuh(_LINUX_EXEC_RULES_DST)
                logger.info("published Linux execve Manager rules %s", _LINUX_EXEC_RULES_DST)
                subprocess.run(
                    ["/var/ossec/bin/wazuh-control", "restart"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
        except OSError as exc:
            logger.warning("skip Linux execve Manager rules: %s", exc)

    if not shared_root.is_dir():
        return
    for group_dir in shared_root.iterdir():
        if not group_dir.is_dir() or group_dir.name in ("agent-template",):
            continue
        if helper is not None:
            dest = group_dir / "install-mssp-linux-telemetry.sh"
            try:
                dest.write_bytes(helper.read_bytes())
                try:
                    dest.chmod(0o640)
                except OSError:
                    pass
                _chown_wazuh(dest)
            except OSError as exc:
                logger.warning("skip shared linux telemetry %s: %s", dest, exc)
        conf_path = group_dir / "agent.conf"
        try:
            current = conf_path.read_text(encoding="utf-8") if conf_path.is_file() else ""
        except OSError:
            continue
        if "mssp-linux-exec-localfile" in current:
            continue
        try:
            new = current.rstrip() + "\n" + _LINUX_EXEC_AGENT_CONF if current.strip() else _LINUX_EXEC_AGENT_CONF
            conf_path.write_text(new, encoding="utf-8")
        except OSError as exc:
            logger.warning("skip shared linux agent.conf %s: %s", conf_path, exc)
            continue
        try:
            conf_path.chmod(0o660)
        except OSError:
            pass
        _chown_wazuh(conf_path)


def _ensure_local_edr_ar_commands() -> None:
    """Register isolate/kill/block-hash command names on the local Manager."""
    try:
        _publish_windows_edr_ar_shared()
    except OSError as exc:
        logger.warning("shared AR publish skipped: %s", exc)
    try:
        _publish_linux_midlayer_shared()
    except OSError as exc:
        logger.warning("linux mid-layer publish skipped: %s", exc)
    conf = Path("/var/ossec/etc/ossec.conf")
    if not conf.is_file():
        return
    text = conf.read_text(encoding="utf-8")
    original = text
    # Timed delete after isolate must never be allowed. Patch older golden images.
    text = text.replace(
        "<name>mssp-isolate-host</name>\n    <executable>mssp-isolate-host</executable>\n    <timeout_allowed>yes</timeout_allowed>",
        "<name>mssp-isolate-host</name>\n    <executable>mssp-isolate-host</executable>\n    <timeout_allowed>no</timeout_allowed>",
    )
    if "<name>mssp-isolate-host.cmd</name>" in text and "<name>mssp-isolate-host</name>" in text:
        if text != original:
            try:
                bak = conf.with_suffix(conf.suffix + ".bak.mssp-edr")
                if not bak.is_file():
                    bak.write_text(original, encoding="utf-8")
                conf.write_text(text, encoding="utf-8")
            except OSError as exc:
                logger.warning("cannot patch ossec.conf (%s); isolate still dispatched", exc)
                return
            subprocess.run(
                ["/var/ossec/bin/wazuh-control", "restart"],
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
            logger.info("disabled Wazuh timed-delete on isolate commands")
        return
    marker = "</ossec_config>"
    idx = text.rfind(marker)
    if idx < 0:
        logger.warning("ossec.conf missing </ossec_config>; cannot register EDR AR")
        return
    bak = conf.with_suffix(conf.suffix + ".bak.mssp-edr")
    try:
        if not bak.is_file():
            bak.write_text(text, encoding="utf-8")
        conf.write_text(text[:idx] + _EDR_AR_COMMAND_BLOCK + "\n" + text[idx:], encoding="utf-8")
    except OSError as exc:
        logger.warning("cannot register EDR AR in ossec.conf (%s); isolate still dispatched", exc)
        return
    subprocess.run(
        ["/var/ossec/bin/wazuh-control", "restart"],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    logger.info("registered MSSP EDR active-response commands on local Manager")


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

    try:
        _ensure_local_edr_ar_commands()
        result["edr_ar_commands"] = "ensured"
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"edr_ar: {exc}")

    # Persist expected group for operators
    try:
        state.ensure_dirs()
        (state.state_root() / "wazuh_agent_group").write_text(group + "\n", encoding="utf-8")
    except Exception:
        pass

    # Enable local→cloud critical-alert forwarder (future default for appliance model)
    try:
        unit = Path("/etc/systemd/system/kevantic-critical-alert-forwarder.service")
        if not unit.is_file():
            # Best-effort copy from payload tree if present on image
            for candidate in (
                Path("/opt/kevantic/payload/configs/systemd/kevantic-critical-alert-forwarder.service"),
                Path("/opt/kevantic/appliance-src/../configs/systemd/kevantic-critical-alert-forwarder.service"),
            ):
                if candidate.is_file():
                    unit.write_text(candidate.read_text(encoding="utf-8"), encoding="utf-8")
                    break
        if unit.is_file():
            base = str(app.get("control_plane") or "").rstrip("/")
            if base:
                env_path = Path("/etc/kevantic/appliance.env")
                env_path.parent.mkdir(parents=True, exist_ok=True)
                lines = []
                if env_path.is_file():
                    lines = env_path.read_text(encoding="utf-8").splitlines()
                kv = {
                    "KEVANTIC_TELEMETRY_URL": f"{base}/api/v1/telemetry/ingest",
                    "KEVANTIC_APPLIANCE_ID": str(app.get("appliance_id") or ""),
                    "KEVANTIC_FORWARD_MIN_LEVEL": "10",
                }
                out_lines = []
                seen = set()
                for line in lines:
                    if "=" in line and not line.strip().startswith("#"):
                        k = line.split("=", 1)[0].strip()
                        if k in kv:
                            out_lines.append(f"{k}={kv[k]}")
                            seen.add(k)
                            continue
                    out_lines.append(line)
                for k, v in kv.items():
                    if k not in seen and v:
                        out_lines.append(f"{k}={v}")
                env_path.write_text("\n".join(out_lines).rstrip() + "\n", encoding="utf-8")
                env_path.chmod(0o640)
            subprocess.run(["systemctl", "daemon-reload"], check=False, timeout=30)
            subprocess.run(
                ["systemctl", "enable", "--now", "kevantic-critical-alert-forwarder.service"],
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
            st = subprocess.run(
                ["systemctl", "is-active", "kevantic-critical-alert-forwarder.service"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            result["critical_alert_forwarder"] = (st.stdout or "").strip() or "unknown"
        else:
            result["critical_alert_forwarder"] = "unit_missing"
            result["errors"].append(
                "critical-alert forwarder unit missing; run "
                "kevantic-appliance/scripts/install_critical_alert_forwarder.sh"
            )
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"critical_alert_forwarder: {exc}")
        result["critical_alert_forwarder"] = "error"

    return result


def _read_enabled_services() -> list[str]:
    ents = state.load_entitlements()
    svcs: list[str] = []
    seen: set[str] = set()
    for raw in ents.get("service_ids") or []:
        sid = str(raw).strip().lower()
        if sid and sid not in seen:
            seen.add(sid)
            svcs.append(sid)
    if _local_manager_active() and "svc-01" not in seen:
        svcs.insert(0, "svc-01")
    elif not svcs and bool(ents.get("core", True)):
        svcs = ["svc-01"]
    return svcs


def _local_manager_active() -> bool:
    try:
        proc = subprocess.run(
            ["systemctl", "is-active", "wazuh-manager"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return (proc.stdout or "").strip() == "active"
    except Exception:
        return False


def _maybe_seed_core_entitlements() -> None:
    ents = state.load_entitlements()
    if ents.get("service_ids"):
        return
    if not _local_manager_active():
        return
    try:
        state.save_entitlements(
            {
                **ents,
                "service_ids": ["svc-01"],
                "core": True,
                "note": "Auto-seeded core entitlement (local Manager active)",
            }
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not seed core entitlements: %s", exc)


def _collect_resource_metrics() -> dict[str, Optional[float]]:
    metrics: dict[str, Optional[float]] = {
        "cpu_percent": None,
        "memory_percent": None,
        "disk_percent": None,
    }
    try:
        meminfo: dict[str, int] = {}
        with Path("/proc/meminfo").open("r", encoding="utf-8") as fh:
            for line in fh:
                key, value = line.split(":", 1)
                meminfo[key.strip()] = int(value.split()[0])
        total = meminfo.get("MemTotal", 0)
        avail = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
        if total > 0:
            metrics["memory_percent"] = round(100.0 * (1 - avail / total), 1)
    except Exception as exc:  # noqa: BLE001
        logger.debug("memory metric unavailable: %s", exc)

    try:
        st = os.statvfs("/")
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        if total > 0:
            metrics["disk_percent"] = round(100.0 * (1 - free / total), 1)
    except Exception as exc:  # noqa: BLE001
        logger.debug("disk metric unavailable: %s", exc)

    try:
        import time

        def _cpu_idle_total() -> tuple[int, int]:
            with Path("/proc/stat").open("r", encoding="utf-8") as fh:
                parts = fh.readline().split()
            nums = [int(x) for x in parts[1:]]
            idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
            return idle, sum(nums)

        idle1, total1 = _cpu_idle_total()
        time.sleep(0.1)
        idle2, total2 = _cpu_idle_total()
        dt = total2 - total1
        di = idle2 - idle1
        if dt > 0:
            metrics["cpu_percent"] = round(max(0.0, min(100.0, 100.0 * (1 - di / dt))), 1)
    except Exception as exc:  # noqa: BLE001
        logger.debug("cpu metric unavailable: %s", exc)

    return metrics


def _read_image_metadata(app: dict[str, Any]) -> dict[str, str]:
    meta = {
        "config_version": str(app.get("config_version") or "track1"),
        "git_commit": str(app.get("git_commit") or ""),
    }
    for candidate in (
        state.config_root() / "image-release.json",
        Path("/etc/junexis/image-release.json"),
        Path("/etc/kevantic/image-release.json"),
    ):
        if not candidate.is_file():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
            if data.get("config_version"):
                meta["config_version"] = str(data["config_version"])
            commit = data.get("git_commit") or data.get("version") or ""
            if commit:
                meta["git_commit"] = str(commit)
            break
        except Exception as exc:  # noqa: BLE001
            logger.debug("image metadata read failed for %s: %s", candidate, exc)
    env_commit = os.environ.get("KEVANTIC_GIT_COMMIT") or os.environ.get("JUNEXIS_GIT_COMMIT")
    if env_commit:
        meta["git_commit"] = env_commit.strip()
    return meta


def _collect_agent_inventory() -> list[dict[str, Any]]:
    """Best-effort local Manager agent list via wazuh-control / API if present."""
    for helper_path in _AGENT_INVENTORY_HELPERS:
        helper = Path(helper_path)
        if not helper.is_file():
            continue
        try:
            out = subprocess.check_output([str(helper)], timeout=20, text=True)
            data = json.loads(out)
            if isinstance(data, list):
                return data
            logger.warning("agent inventory helper %s returned non-list JSON", helper)
        except Exception as exc:  # noqa: BLE001 — keep heartbeat alive
            logger.warning("agent inventory helper %s failed: %s", helper, exc)
    # Optional: Wazuh API on localhost (default appliance Manager)
    try:
        token = _authenticate_local_wazuh()
        agents_resp = _wazuh_local_json(
            "GET",
            "/agents?limit=500&select=id,name,status,ip,os.name,os.platform,lastKeepAlive",
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
    try:
        try:
            _ensure_local_edr_ar_commands()
        except OSError as exc:
            logger.warning("ensure AR commands skipped: %s", exc)
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
            return False, detail or f"Active response failed for agent {agent_id}"
        return True, f"AR {command} dispatched to agent {agent_id}"
    except Exception as exc:
        return False, str(exc)[:300]


def _dispatch_job(job: dict[str, Any]) -> tuple[bool, str]:
    """Route pending control-plane jobs to the correct local handler."""
    job_type = str(job.get("job_type") or "").strip()
    payload = job.get("payload") or {}
    if job_type == "set_agent_cidrs":
        network_ops = _cli_submodule("network")
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
    if job_type == "apply_entitlements":
        raw_ids = payload.get("service_ids") or []
        service_ids: list[str] = []
        seen: set[str] = set()
        for raw in raw_ids:
            sid = str(raw).strip().lower()
            if sid and sid not in seen:
                seen.add(sid)
                service_ids.append(sid)
        if "svc-01" not in seen:
            service_ids.insert(0, "svc-01")
        ents = state.load_entitlements()
        state.save_entitlements(
            {
                **ents,
                "service_ids": service_ids,
                "core": "svc-01" in service_ids,
                "order_number": payload.get("order_number"),
                "catalog_key": payload.get("catalog_key"),
            }
        )
        reconcile: dict[str, Any] | None = None
        for helper in (
            "/usr/bin/junexis-reconcile-services",
            "/usr/bin/kevantic-reconcile-services",
        ):
            if not Path(helper).is_file():
                continue
            try:
                proc = subprocess.run(
                    [helper],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=120,
                )
            except Exception as exc:  # noqa: BLE001
                reconcile = {"error": str(exc)[:200]}
                break
            try:
                reconcile = json.loads(proc.stdout or "{}")
            except json.JSONDecodeError:
                reconcile = {
                    "stdout": (proc.stdout or "")[:300],
                    "stderr": (proc.stderr or "")[:300],
                    "rc": proc.returncode,
                }
            break
        return True, json.dumps({"service_ids": service_ids, "reconcile": reconcile})[:500]
    # Default: Active Response / isolate-style jobs
    if payload.get("ar_command") or payload.get("agent_id"):
        return _run_local_ar(job)
    return False, f"unsupported job_type: {job_type or 'missing'}"


def _load_agent_cidrs_safe() -> list[str]:
    try:
        return list(_cli_submodule("network").load_agent_cidrs() or [])
    except Exception:
        return []


def heartbeat(*, include_inventory: bool = True) -> dict[str, Any]:
    app = state.load_appliance_state()
    appliance_id = app.get("appliance_id")
    if not appliance_id:
        raise RuntimeError("not registered; run kevantic-cli register first")
    try:
        _publish_windows_edr_ar_shared()
    except Exception:
        pass
    _maybe_seed_core_entitlements()
    api_key = load_api_key()
    base = _control_plane_base(app)
    image_meta = _read_image_metadata(app)
    metrics = _collect_resource_metrics()
    body: dict[str, Any] = {
        "health_status": "healthy",
        "local_ip": app.get("local_ip") or _guess_local_ip(),
        "agent_version": "0.1.0-dev",
        "config_version": image_meta["config_version"],
        "git_commit": image_meta["git_commit"] or None,
        "enabled_services": _read_enabled_services(),
        "cpu_percent": metrics["cpu_percent"],
        "memory_percent": metrics["memory_percent"],
        "disk_percent": metrics["disk_percent"],
        "health_snapshot": {
            "source": "kevantic-cli",
            "agent_source_cidrs": _load_agent_cidrs_safe(),
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
