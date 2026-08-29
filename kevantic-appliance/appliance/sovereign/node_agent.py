"""Minimal Sovereign cluster node health API (stdlib only)."""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from appliance.sovereign.cluster import (
    _load_meta,
    apply_remote_heartbeat,
    cluster_status,
    node_state_dir,
    physical_state_dir,
    record_heartbeat,
    sync_from_shared,
)


class _Handler(BaseHTTPRequestHandler):
    node_id: str = "a"

    def _json(self, code: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        meta = _load_meta()
        if not meta:
            return True
        token = str(meta.get("join_token") or "")
        if not token:
            return True
        return (self.headers.get("X-Sovereign-Join-Token") or "") == token

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: D401
        return

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            self._json(200, {"ok": True, "node_id": self.node_id})
            return
        if path == "/cluster/status":
            self._json(200, cluster_status(self.node_id))
            return
        if path.startswith("/cluster/artifact/"):
            if not self._authorized():
                self._json(403, {"error": "forbidden"})
                return
            name = path.rsplit("/", 1)[-1]
            src = node_state_dir(self.node_id) / name
            if not src.is_file():
                self._json(404, {"error": "not_found"})
                return
            body = src.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if not self._authorized():
            self._json(403, {"error": "forbidden"})
            return
        if path == "/cluster/sync":
            try:
                self._json(200, sync_from_shared(self.node_id))
            except Exception as exc:  # noqa: BLE001
                self._json(400, {"ok": False, "error": str(exc)[:200]})
            return
        if path == "/cluster/heartbeat":
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
                remote_id = str(payload.get("node_id") or "")
                seen = int(payload.get("last_seen_at") or time.time())
                self._json(200, apply_remote_heartbeat(remote_id, seen))
            except Exception as exc:  # noqa: BLE001
                self._json(400, {"ok": False, "error": str(exc)[:200]})
            return
        if path.startswith("/cluster/artifact/"):
            name = path.rsplit("/", 1)[-1]
            length = int(self.headers.get("Content-Length") or 0)
            data = self.rfile.read(length) if length else b""
            dest_root = node_state_dir(self.node_id)
            dest_root.mkdir(parents=True, exist_ok=True)
            dest = dest_root / name
            tmp = dest.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(dest)
            self._json(200, {"ok": True, "artifact": name, "bytes": len(data)})
            return
        self._json(404, {"error": "not_found"})


def _heartbeat_loop(node_id: str, interval: int) -> None:
    while True:
        try:
            record_heartbeat(node_id)
        except Exception:
            pass
        time.sleep(max(1, interval))


def serve(node_id: str, port: int, bind_host: str, heartbeat_seconds: int = 10) -> None:
    handler_cls = type("NodeHandler", (_Handler,), {"node_id": node_id})
    server = ThreadingHTTPServer((bind_host, port), handler_cls)
    record_heartbeat(node_id)
    thread = threading.Thread(target=_heartbeat_loop, args=(node_id, heartbeat_seconds), daemon=True)
    thread.start()
    server.serve_forever()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Sovereign cluster node agent")
    parser.add_argument("--node-id", required=True, choices=["a", "b"])
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--bind", default="")
    parser.add_argument("--heartbeat-seconds", type=int, default=10)
    args = parser.parse_args(argv)
    port = args.port or 8443
    bind = args.bind.strip() or os.environ.get("SOVEREIGN_NODE_BIND", "127.0.0.1")
    if os.environ.get("SOVEREIGN_CLUSTER_TOPOLOGY") == "multihost":
        bind = args.bind.strip() or os.environ.get("SOVEREIGN_NODE_BIND", "0.0.0.0")
    physical_state_dir().mkdir(parents=True, exist_ok=True)
    serve(args.node_id, port, bind, heartbeat_seconds=args.heartbeat_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
