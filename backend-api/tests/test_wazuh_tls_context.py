"""Wazuh API TLS: production fail-closed + pinned CA without hostname when dialing by IP."""

from __future__ import annotations

import os
import ssl
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import wazuh_client


class WazuhTlsContextTests(unittest.TestCase):
    def test_production_requires_verify(self):
        with patch.dict(
            os.environ,
            {"APP_ENV": "production", "WAZUH_API_VERIFY_TLS": "false"},
            clear=False,
        ):
            with self.assertRaises(wazuh_client.WazuhTlsConfigurationError):
                wazuh_client.validate_production_tls()

    def test_verify_with_ca_disables_hostname_by_default(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            ca = Path(tmp) / "ca.crt"
            key = Path(tmp) / "key.pem"
            subprocess.run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-keyout",
                    str(key),
                    "-out",
                    str(ca),
                    "-days",
                    "1",
                    "-nodes",
                    "-subj",
                    "/CN=wazuh-tls-unit-test",
                ],
                check=True,
                capture_output=True,
            )
            env = {
                "APP_ENV": "production",
                "WAZUH_API_VERIFY_TLS": "true",
                "WAZUH_API_CA_FILE": str(ca),
                "WAZUH_API_TLS_CHECK_HOSTNAME": "false",
            }
            with patch.dict(os.environ, env, clear=False):
                ctx = wazuh_client._ssl_context()
                self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
                self.assertFalse(ctx.check_hostname)


if __name__ == "__main__":
    unittest.main()
