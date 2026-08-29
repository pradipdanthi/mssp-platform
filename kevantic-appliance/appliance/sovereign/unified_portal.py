"""Unified Sovereign Edge portal gateway (single origin, RBAC-enforced)."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from appliance.sovereign.full_stack import DEFAULT_PORTAL_PORT, load_manifest
from appliance.sovereign.portal_auth import login_response, parse_bearer_authorization, verify_access_token
from appliance.sovereign.rbac import sovereign_http_status_for_deny, sovereign_route_access

PUBLIC_GET_PATHS = frozenset({"/health", "/api/v1/health"})
PUBLIC_POST_PATHS = frozenset({"/auth/login", "/api/v1/auth/login"})


def _portal_html(role: str) -> str:
    engineer = role in {"platform_admin", "soc_manager", "soc_analyst"}
    links = ""
    if engineer:
        links = """
        <li><a href="/proxy/thehive/">TheHive (local)</a></li>
        <li><a href="/proxy/shuffle/">Shuffle SOAR (local)</a></li>
        <li><a href="/admin/tenants">Admin — Tenants</a></li>
        """
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>NikTiar Sovereign Edge</title></head>
<body>
<h1>NikTiar Sovereign Edge — Unified Portal</h1>
<p>Role: <code>{role}</code></p>
<ul>
  <li><a href="/health">Health</a></li>
  <li><a href="/customer/incidents">Customer incidents</a></li>
  {links}
</ul>
</body></html>"""


class UnifiedPortalHandler(BaseHTTPRequestHandler):
    manifest: Dict[str, Any] = {}

    def _read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _json(self, code: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, code: int, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _resolve_role(self, method: str, path: str) -> Tuple[Optional[str], Optional[int]]:
        """Return (role, error_http_status). error status 401/403 when blocked."""
        if method == "GET" and path in PUBLIC_GET_PATHS:
            return None, None
        if method == "POST" and path in PUBLIC_POST_PATHS:
            return None, None

        token = parse_bearer_authorization(self.headers.get("Authorization"))
        if not token:
            return None, 401

        claims = verify_access_token(token)
        if not claims:
            return None, 401

        role = str(claims.get("role") or "")
        deny = self._enforce_role(role, method, path)
        if deny:
            return None, deny
        return role, None

    def _enforce_role(self, role: str, method: str, path: str) -> Optional[int]:
        allowed, _reason = sovereign_route_access(role, method, path)
        if allowed:
            return None
        return sovereign_http_status_for_deny(_reason)

    def _proxy(self, upstream_base: str, suffix: str) -> None:
        url = f"{upstream_base.rstrip('/')}/{suffix.lstrip('/')}"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type", resp.headers.get("Content-Type", "application/json"))
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        except urllib.error.HTTPError as exc:
            body = exc.read()
            self.send_response(exc.code)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:  # noqa: BLE001
            self._json(502, {"error": "upstream_unavailable", "detail": str(exc)[:200]})

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        role, err = self._resolve_role("GET", path)
        if err:
            self._json(err, {"error": "unauthorized" if err == 401 else "forbidden", "path": path})
            return

        if path in {"/health", "/api/v1/health"}:
            self._json(200, {"ok": True, "service": "sovereign-unified-portal", "authenticated": role is not None})
            return

        if path in {"/", "/portal"}:
            self._html(200, _portal_html(role or "anonymous"))
            return

        if path in {"/customer/incidents", "/api/v1/customer/incidents"}:
            self._json(200, {"incidents": [], "source": "local_sovereign_edge"})
            return

        if path.startswith("/admin/"):
            self._json(200, {"tenants": [], "source": "local_sovereign_edge_admin"})
            return

        if path.startswith("/proxy/thehive/"):
            base = str(self.manifest.get("thehive_url") or "http://127.0.0.1:9000")
            self._proxy(base, path[len("/proxy/thehive/") :])
            return

        if path.startswith("/proxy/shuffle/"):
            base = str(self.manifest.get("shuffle_url") or "http://127.0.0.1:3001")
            self._proxy(base, path[len("/proxy/shuffle/") :])
            return

        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in {"/auth/login", "/api/v1/auth/login"}:
            body = self._read_json_body()
            code, payload = login_response(
                str(body.get("username") or ""),
                str(body.get("password") or ""),
            )
            self._json(code, payload)
            return

        role, err = self._resolve_role("POST", path)
        if err:
            self._json(err, {"error": "unauthorized" if err == 401 else "forbidden", "path": path})
            return
        self._json(200, {"ok": True, "path": path})


def serve(port: Optional[int] = None) -> None:
    manifest = load_manifest()
    bind_port = port or int(manifest.get("unified_portal_port") or DEFAULT_PORTAL_PORT)
    handler_cls = type("BoundHandler", (UnifiedPortalHandler,), {"manifest": manifest})
    server = ThreadingHTTPServer(("127.0.0.1", bind_port), handler_cls)
    server.serve_forever()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Sovereign unified portal gateway")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args(argv)
    serve(args.port or None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
