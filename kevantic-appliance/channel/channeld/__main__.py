"""kevantic-channeld — outbound SOC channel client (Phase B).

Connects to control plane / Appliance Management gateway via:
1. WebSocket /appliance/v1/channel (preferred)
2. HTTPS poll /appliance/channel/poll (fallback)

Handles job / license.push / ota.offer / control frames.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

LOG = logging.getLogger("kevantic-channeld")


def _state_root() -> Path:
    return Path(
        os.environ.get("KEVANTIC_STATE_DIR")
        or os.environ.get("JUNEXIS_STATE_DIR")
        or ("/var/lib/junexis" if Path("/var/lib/junexis/appliance.json").is_file() else "/var/lib/kevantic")
    )


def _config_root() -> Path:
    return Path(
        os.environ.get("KEVANTIC_CONFIG_DIR")
        or os.environ.get("JUNEXIS_CONFIG_DIR")
        or ("/etc/junexis" if Path("/etc/junexis").is_dir() else "/etc/kevantic")
    )


def load_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    raw = path.read_text(encoding="utf-8")
    # Minimal YAML-ish or JSON
    raw = raw.strip()
    if raw.startswith("{"):
        return json.loads(raw)
    cfg: dict[str, Any] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        cfg[k.strip()] = v.strip().strip("\"'")
    return cfg


def load_creds() -> tuple[str, str]:
    app_path = _state_root() / "appliance.json"
    key_path = _state_root() / "secrets" / "appliance_api_key"
    appliance_id = ""
    if app_path.is_file():
        appliance_id = str(json.loads(app_path.read_text()).get("appliance_id") or "")
    appliance_id = (
        os.environ.get("KEVANTIC_APPLIANCE_ID")
        or os.environ.get("JUNEXIS_APPLIANCE_ID")
        or appliance_id
    )
    api_key = (
        os.environ.get("KEVANTIC_APPLIANCE_API_KEY")
        or os.environ.get("JUNEXIS_APPLIANCE_API_KEY")
        or ""
    )
    if not api_key and key_path.is_file():
        api_key = key_path.read_text(encoding="utf-8").strip()
    if not appliance_id or not api_key:
        raise RuntimeError("missing appliance_id or API key (register first)")
    return appliance_id, api_key


def control_plane_base(cfg: dict[str, Any]) -> str:
    base = (
        cfg.get("control_plane")
        or os.environ.get("KEVANTIC_CONTROL_PLANE")
        or os.environ.get("JUNEXIS_CONTROL_PLANE")
        or ""
    )
    if not base and (_state_root() / "appliance.json").is_file():
        base = str(json.loads((_state_root() / "appliance.json").read_text()).get("control_plane") or "")
    base = base.rstrip("/")
    if not base:
        raise RuntimeError("control_plane URL not configured")
    if base.endswith("/api"):
        base = base[:-4]
    return base


def _ssl_context() -> ssl.SSLContext:
    verify = (
        os.environ.get("KEVANTIC_TLS_VERIFY")
        or os.environ.get("JUNEXIS_TLS_VERIFY")
        or "true"
    ).lower() not in (
        "0",
        "false",
        "no",
    )
    if verify:
        return ssl.create_default_context()
    ctx = ssl._create_unverified_context()
    return ctx


def http_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    body: Optional[dict] = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    data = None
    hdrs = dict(headers)
    if body is not None:
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    with urllib.request.urlopen(req, context=_ssl_context(), timeout=timeout) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def handle_frame(frame: dict[str, Any], *, base: str, headers: dict[str, str]) -> dict[str, Any]:
    """Process one inbound frame; return ack payload."""
    ftype = frame.get("type")
    payload = frame.get("payload") or {}
    fid = frame.get("id")
    LOG.info("frame type=%s id=%s", ftype, fid)

    if ftype == "job":
        # Execute via local engine API when possible
        job_id = payload.get("job_id") or fid
        try:
            # Prefer local engine execute if job already known; else stage AR via heartbeat path
            try:
                from kevantic_cli import register_ops  # type: ignore
            except ImportError:
                from junexis_cli import register_ops  # type: ignore

            # Reuse AR runner for containment-style jobs
            ok, msg = register_ops._run_local_ar({"payload": payload})
            return {"ref": fid, "job_id": job_id, "success": ok, "message": msg}
        except Exception as exc:
            return {"ref": fid, "job_id": job_id, "success": False, "message": str(exc)[:300]}

    if ftype == "license.push":
        token = payload.get("jws") or payload.get("license") or ""
        if not token:
            return {"ref": fid, "success": False, "message": "missing license jws"}
        path = _state_root() / "ota" / f"license-push-{int(time.time())}.jws"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(token.strip() + "\n", encoding="utf-8")
        try:
            from kevantic_cli.license_ops import apply_license_file

            apply_license_file(path)
            return {"ref": fid, "success": True, "message": "license applied"}
        except Exception as exc:
            return {"ref": fid, "success": False, "message": str(exc)[:300]}

    if ftype == "ota.offer":
        try:
            from kevantic_ota import apply_offer

            result = apply_offer(payload)
            return {"ref": fid, "success": bool(result.get("ok")), "result": result}
        except Exception as exc:
            return {"ref": fid, "success": False, "message": str(exc)[:300]}

    if ftype in ("control", "heartbeat"):
        return {"ref": fid, "success": True, "message": "ok"}

    return {"ref": fid, "success": True, "message": f"ignored type {ftype}"}


def send_acks(base: str, headers: dict[str, str], acks: list[dict[str, Any]]) -> None:
    if not acks:
        return
    frames = []
    for ack in acks:
        frames.append(
            {
                "v": 1,
                "type": "ack",
                "id": str(uuid4()),
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "payload": ack,
            }
        )
    # Also send heartbeat status
    frames.append(
        {
            "v": 1,
            "type": "heartbeat",
            "id": str(uuid4()),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "payload": {"source": "kevantic-channeld", "ok": True},
        }
    )
    http_json(
        "POST",
        f"{base}/appliance/channel/frames",
        headers=headers,
        body={"frames": frames},
    )


def run_poll_loop(cfg: dict[str, Any]) -> int:
    appliance_id, api_key = load_creds()
    base = control_plane_base(cfg)
    headers = {
        "X-Appliance-ID": appliance_id,
        "X-Appliance-API-Key": api_key,
        "Accept": "application/json",
        "User-Agent": "kevantic-channeld/0.1",
    }
    interval = int(cfg.get("poll_interval_sec") or os.environ.get("KEVANTIC_CHANNEL_POLL_SEC") or 20)
    status_path = _state_root() / "channeld.status.json"
    LOG.info("channeld poll mode control_plane=%s interval=%ss", base, interval)

    while True:
        try:
            bundle = http_json("GET", f"{base}/appliance/channel/poll", headers=headers)
            frames = bundle.get("frames") or []
            acks = []
            for frame in frames:
                acks.append(handle_frame(frame, base=base, headers=headers))
            send_acks(base, headers, acks)
            status_path.write_text(
                json.dumps(
                    {
                        "mode": "https_poll",
                        "ok": True,
                        "last_poll_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "frames": len(frames),
                        "control_plane": base,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        except Exception as exc:
            LOG.warning("poll error: %s", exc)
            status_path.write_text(
                json.dumps(
                    {
                        "mode": "https_poll",
                        "ok": False,
                        "error": str(exc)[:300],
                        "last_poll_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        time.sleep(interval)


def run_ws_loop(cfg: dict[str, Any]) -> int:
    """Optional websocket mode when `websocket-client` is installed."""
    try:
        import websocket  # type: ignore
    except ImportError:
        LOG.info("websocket-client not installed; using HTTPS poll")
        return run_poll_loop(cfg)

    appliance_id, api_key = load_creds()
    base = control_plane_base(cfg)
    ws_url = cfg.get("channel_ws") or base.replace("https://", "wss://").replace("http://", "ws://")
    if not ws_url.rstrip("/").endswith("/appliance/v1/channel"):
        ws_url = ws_url.rstrip("/") + "/appliance/v1/channel"
    LOG.info("channeld websocket mode url=%s", ws_url)
    status_path = _state_root() / "channeld.status.json"

    def on_message(ws, message):  # noqa: ANN001
        try:
            frame = json.loads(message)
        except Exception:
            return
        headers = {
            "X-Appliance-ID": appliance_id,
            "X-Appliance-API-Key": api_key,
            "Accept": "application/json",
        }
        ack = handle_frame(frame, base=base, headers=headers)
        ws.send(
            json.dumps(
                {
                    "v": 1,
                    "type": "ack",
                    "id": str(uuid4()),
                    "payload": ack,
                }
            )
        )
        status_path.write_text(
            json.dumps(
                {
                    "mode": "websocket",
                    "ok": True,
                    "last_frame_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "control_plane": base,
                },
                indent=2,
            )
            + "\n"
        )

    def on_error(ws, error):  # noqa: ANN001
        LOG.warning("ws error: %s", error)

    def on_open(ws):  # noqa: ANN001
        ws.send(
            json.dumps(
                {
                    "v": 1,
                    "type": "heartbeat",
                    "id": str(uuid4()),
                    "payload": {"source": "kevantic-channeld", "hello": True},
                }
            )
        )

    header = [f"X-Appliance-ID: {appliance_id}", f"X-Appliance-API-Key: {api_key}"]
    sslopt = {}
    tls_verify = (
        os.environ.get("KEVANTIC_TLS_VERIFY")
        or os.environ.get("JUNEXIS_TLS_VERIFY")
        or "true"
    )
    if (tls_verify or "true").lower() in ("0", "false", "no"):
        sslopt = {"cert_reqs": ssl.CERT_NONE}
    ws_app = websocket.WebSocketApp(
        ws_url,
        header=header,
        on_message=on_message,
        on_error=on_error,
        on_open=on_open,
    )
    # run_forever reconnects; on hard failure fall back to poll
    try:
        ws_app.run_forever(sslopt=sslopt, ping_interval=20, ping_timeout=10)
    except Exception as exc:
        LOG.warning("websocket failed (%s); falling back to poll", exc)
        return run_poll_loop(cfg)
    return run_poll_loop(cfg)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    p = argparse.ArgumentParser(prog="kevantic-channeld")
    p.add_argument("--config", default="/etc/kevantic/channel.yaml")
    p.add_argument("--mode", choices=["auto", "poll", "websocket"], default="auto")
    args = p.parse_args(argv)
    cfg = load_config(Path(args.config))
    _state_root().mkdir(parents=True, exist_ok=True)
    mode = args.mode
    if mode == "auto":
        mode = str(cfg.get("mode") or "auto")
    try:
        if mode == "poll":
            return run_poll_loop(cfg)
        if mode == "websocket":
            return run_ws_loop(cfg)
        # auto: try websocket briefly then poll is safer for lab without ws client
        return run_ws_loop(cfg)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
