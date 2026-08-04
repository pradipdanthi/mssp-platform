"""Local appliance REST surface for cloud-submitted jobs (LAN-only / loopback)."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from appliance.hunting.retrospective_sweeper import RetrospectiveSweeper


class ApplianceAPIHandler(BaseHTTPRequestHandler):
    sweeper = RetrospectiveSweeper()

    def log_message(self, fmt: str, *args: Any) -> None:  # quieter
        return

    def _json(self, code: int, body: dict[str, Any]) -> None:
        raw = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path.startswith("/appliance/v1/jobs/retrospective-hunt/"):
            job_id = path.rsplit("/", 1)[-1]
            job = self.sweeper.get_job(job_id)
            if not job:
                self._json(404, {"detail": "job not found"})
                return
            self._json(200, job)
            return
        if path in {"/health", "/appliance/v1/health"}:
            self._json(200, {"status": "ok", "service": "junexis-appliance-engine"})
            return
        self._json(404, {"detail": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._json(400, {"detail": "invalid json"})
            return

        if path == "/appliance/v1/jobs/retrospective-hunt":
            try:
                result = self.sweeper.run_job(payload)
                self._json(200, result)
            except ValueError as exc:
                self._json(400, {"detail": str(exc)})
            except Exception as exc:  # noqa: BLE001
                self._json(500, {"detail": str(exc)})
            return
        self._json(404, {"detail": "not found"})


def serve(host: str = "127.0.0.1", port: int = 8787) -> None:
    """
    Bind loopback by default — cloud reaches this via outbound channel / SSH tunnel,
    not a public inbound WAN port (KB-093 locked posture).
    """
    httpd = ThreadingHTTPServer((host, port), ApplianceAPIHandler)
    print(f"junexis appliance engine API on http://{host}:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    serve()
