"""Authenticated, certificate-validated transport to the SOC agent (LOCAL tests, loopback only).

Generates a throwaway CA and server certificate with scripts/tia_tls_setup.sh, serves a
stub agent over TLS on 127.0.0.1, and checks that the control-plane client verifies it.
No real certificate, key, token or host is involved.
"""

from __future__ import annotations

import http.server
import json
import os
import ssl
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from app.services import soc_agent_client as client
from app.services import tia_schema

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "tia_tls_setup.sh"


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = json.dumps({"ok": True}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # noqa: D401
        pass


class TransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not SCRIPT.exists():
            raise RuntimeError(f"missing {SCRIPT}; the test image must mount the repository scripts/ directory")
        cls.tmp = tempfile.TemporaryDirectory()
        out = os.path.join(cls.tmp.name, "tls")
        other = os.path.join(cls.tmp.name, "other-ca")
        env = {**os.environ, "OUT": out, "AGENT_NAMES": "127.0.0.1"}
        subprocess.run(["bash", str(SCRIPT)], check=True, env=env, capture_output=True)
        subprocess.run(["bash", str(SCRIPT)], check=True, env={**env, "OUT": other}, capture_output=True)
        cls.ca = os.path.join(out, "ca.crt")
        cls.other_ca = os.path.join(other, "ca.crt")
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(os.path.join(out, "agent.crt"), os.path.join(out, "agent.key"))
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.server.socket = ctx.wrap_socket(cls.server.socket, server_side=True)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def call(self, host="127.0.0.1", **env):
        base = {"SOC_AGENT_URL": f"https://{host}:{self.port}", "SOC_AGENT_CA_BUNDLE": self.ca}
        base.update(env)
        with patch.dict(os.environ, base):
            req = urllib.request.Request(f"{client.soc_agent_url()}/health")
            with client.open_agent(req, 5) as resp:
                return resp.status

    def test_a_certificate_signed_by_the_pinned_ca_is_accepted(self) -> None:
        self.assertEqual(self.call(), 200)

    def test_the_system_trust_store_does_not_trust_the_internal_ca(self) -> None:
        with self.assertRaises(urllib.error.URLError) as ctx:
            self.call(SOC_AGENT_CA_BUNDLE="")
        self.assertIn("CERTIFICATE_VERIFY_FAILED", str(ctx.exception))

    def test_a_certificate_from_a_different_ca_is_rejected(self) -> None:
        with self.assertRaises(urllib.error.URLError) as ctx:
            self.call(SOC_AGENT_CA_BUNDLE=self.other_ca)
        self.assertIn("CERTIFICATE_VERIFY_FAILED", str(ctx.exception))

    def test_a_hostname_not_in_the_certificate_is_rejected(self) -> None:
        with self.assertRaises(urllib.error.URLError) as ctx:
            self.call(host="localhost")  # SAN contains only IP 127.0.0.1
        self.assertIn("CERTIFICATE_VERIFY_FAILED", str(ctx.exception))

    def test_plaintext_is_refused_when_tls_is_required(self) -> None:
        with patch.dict(os.environ, {"SOC_AGENT_URL": "http://127.0.0.1:1", "SOC_AGENT_REQUIRE_TLS": "true"}):
            req = urllib.request.Request(f"{client.soc_agent_url()}/health")
            with self.assertRaises(urllib.error.URLError) as ctx:
                client.open_agent(req, 2)
        self.assertIn("not encrypted", str(ctx.exception))

    def test_transport_and_readiness_report_plaintext_and_unpinned_ca_honestly(self) -> None:
        with patch.dict(os.environ, {"SOC_AGENT_ENABLED": "true", "SOC_AGENT_URL": "http://192.0.2.10:8443"}):
            self.assertFalse(client.agent_transport()["encrypted"])
            codes = {f["code"]: f["severity"] for f in tia_schema.notification_config_faults()}
            self.assertEqual(codes.get("agent_transport_not_encrypted"), "fault")
        with patch.dict(os.environ, {"SOC_AGENT_ENABLED": "true", "SOC_AGENT_URL": "http://192.0.2.10:8443", "SOC_AGENT_ALLOW_INSECURE_HTTP": "true"}):
            codes = {f["code"]: f["severity"] for f in tia_schema.notification_config_faults()}
            self.assertEqual(codes.get("agent_transport_not_encrypted"), "warning")
        with patch.dict(os.environ, {"SOC_AGENT_ENABLED": "true", "SOC_AGENT_URL": "https://192.0.2.10:8443", "SOC_AGENT_CA_BUNDLE": ""}):
            codes = {f["code"]: f["severity"] for f in tia_schema.notification_config_faults()}
            self.assertNotIn("agent_transport_not_encrypted", codes)
            self.assertEqual(codes.get("agent_ca_not_pinned"), "warning")


if __name__ == "__main__":
    unittest.main()
