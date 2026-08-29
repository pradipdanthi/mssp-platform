"""SEC-001: Sovereign unified portal authentication and header-spoof tests."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "kevantic-appliance"))

from appliance.sovereign import portal_auth  # noqa: E402
from appliance.sovereign.unified_portal import UnifiedPortalHandler  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402


class PortalAuthUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env = os.environ.copy()
        os.environ["SOVEREIGN_PORTAL_LAB_BOOTSTRAP"] = "1"
        os.environ["SOVEREIGN_PORTAL_SOC_USER"] = "soc_engineer"
        os.environ["SOVEREIGN_PORTAL_SOC_PASSWORD"] = "soc-pass-lab"
        os.environ["SOVEREIGN_PORTAL_SOC_ROLE"] = "soc_analyst"
        os.environ["SOVEREIGN_PORTAL_CUSTOMER_USER"] = "customer_viewer"
        os.environ["SOVEREIGN_PORTAL_CUSTOMER_PASSWORD"] = "cust-pass-lab"
        os.environ["SOVEREIGN_PORTAL_CUSTOMER_ROLE"] = "customer_viewer"
        os.environ["SOVEREIGN_PORTAL_LAB_JWT_SECRET"] = "unit-test-jwt-secret"

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env)

    def test_valid_login_issues_token(self):
        code, payload = portal_auth.login_response("soc_engineer", "soc-pass-lab")
        self.assertEqual(code, 200)
        self.assertIn("access_token", payload)
        claims = portal_auth.verify_access_token(payload["access_token"])
        self.assertIsNotNone(claims)
        assert claims is not None
        self.assertEqual(claims["role"], "soc_analyst")

    def test_invalid_credentials_rejected(self):
        code, payload = portal_auth.login_response("soc_engineer", "wrong")
        self.assertEqual(code, 401)
        self.assertEqual(payload.get("error"), "invalid_credentials")

    def test_unknown_user_rejected(self):
        code, payload = portal_auth.login_response("nobody", "wrong")
        self.assertEqual(code, 401)
        self.assertEqual(payload.get("error"), "invalid_credentials")

    def test_expired_token_rejected(self):
        secret = portal_auth.load_jwt_secret()
        assert secret
        past = int(time.time()) - 3600
        token = portal_auth._encode_jwt(
            {"sub": "soc_engineer", "role": "soc_analyst", "iat": past - 10, "exp": past},
            secret,
        )
        self.assertIsNone(portal_auth.verify_access_token(token))

    def test_malformed_token_rejected(self):
        self.assertIsNone(portal_auth.verify_access_token("not.a.jwt"))
        self.assertIsNone(portal_auth.verify_access_token("a.b.c"))

    def test_forged_token_rejected(self):
        token = portal_auth.issue_access_token("soc_engineer", "soc_analyst")
        assert token
        parts = token.split(".")
        payload = json.loads(portal_auth._b64url_decode(parts[1]))
        payload["role"] = "platform_admin"
        forged_payload = portal_auth._b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
        forged = f"{parts[0]}.{forged_payload}.{parts[2]}"
        self.assertIsNone(portal_auth.verify_access_token(forged))

    def test_invalid_role_in_token_rejected(self):
        secret = portal_auth.load_jwt_secret()
        assert secret
        bad = portal_auth._encode_jwt(
            {"sub": "x", "role": "superuser", "exp": int(time.time()) + 3600},
            secret,
        )
        self.assertIsNone(portal_auth.verify_access_token(bad))


class UnifiedPortalHttpTests(unittest.TestCase):
    port = 19443

    @classmethod
    def setUpClass(cls) -> None:
        cls._env = os.environ.copy()
        os.environ["SOVEREIGN_PORTAL_LAB_BOOTSTRAP"] = "1"
        os.environ["SOVEREIGN_PORTAL_SOC_USER"] = "soc_engineer"
        os.environ["SOVEREIGN_PORTAL_SOC_PASSWORD"] = "soc-pass-lab"
        os.environ["SOVEREIGN_PORTAL_SOC_ROLE"] = "soc_analyst"
        os.environ["SOVEREIGN_PORTAL_CUSTOMER_USER"] = "customer_viewer"
        os.environ["SOVEREIGN_PORTAL_CUSTOMER_PASSWORD"] = "cust-pass-lab"
        os.environ["SOVEREIGN_PORTAL_CUSTOMER_ROLE"] = "customer_viewer"
        os.environ["SOVEREIGN_PORTAL_LAB_JWT_SECRET"] = "unit-test-jwt-secret"

        handler_cls = type("TestHandler", (UnifiedPortalHandler,), {"manifest": {}})
        cls._server = ThreadingHTTPServer(("127.0.0.1", cls.port), handler_cls)
        cls._thread = threading.Thread(target=cls._server.serve_forever, daemon=True)
        cls._thread.start()
        time.sleep(0.2)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._server.shutdown()
        os.environ.clear()
        os.environ.update(cls._env)

    def _request(self, method: str, path: str, *, headers=None, body=None):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=body,
            headers=headers or {},
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def _login(self, user: str, password: str) -> str:
        payload = json.dumps({"username": user, "password": password}).encode()
        code, raw = self._request(
            "POST",
            "/auth/login",
            headers={"Content-Type": "application/json"},
            body=payload,
        )
        self.assertEqual(code, 200)
        data = json.loads(raw.decode())
        return data["access_token"]

    def test_header_spoof_does_not_grant_soc_access(self):
        code, _ = self._request(
            "GET",
            "/admin/tenants",
            headers={"X-Sovereign-Role": "soc_analyst"},
        )
        self.assertEqual(code, 401)

    def test_soc_admin_allowed_with_bearer(self):
        token = self._login("soc_engineer", "soc-pass-lab")
        code, _ = self._request(
            "GET",
            "/admin/tenants",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(code, 200)

    def test_customer_admin_denied_admin(self):
        token = self._login("customer_viewer", "cust-pass-lab")
        code, _ = self._request(
            "GET",
            "/admin/tenants",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(code, 403)

    def test_customer_incidents_allowed(self):
        token = self._login("customer_viewer", "cust-pass-lab")
        code, _ = self._request(
            "GET",
            "/api/v1/customer/incidents",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(code, 200)

    def test_anonymous_protected_route_denied(self):
        code, _ = self._request("GET", "/admin/tenants")
        self.assertEqual(code, 401)

    def test_anonymous_health_ok(self):
        code, raw = self._request("GET", "/health")
        self.assertEqual(code, 200)
        data = json.loads(raw.decode())
        self.assertTrue(data.get("ok"))


if __name__ == "__main__":
    unittest.main()
