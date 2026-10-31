"""Access logs must not echo Wazuh ingress tokens embedded in URL paths."""

from __future__ import annotations

import unittest

from app.core.access_log_redact import redact_access_path


class AccessLogRedactTests(unittest.TestCase):
    def test_redacts_wazuh_hook_token(self):
        raw = (
            'INFO: 192.168.0.211:38812 - "POST '
            '/integrations/soc/hooks/wazuh/supersecrettokenvalue123 HTTP/1.1" 200 OK'
        )
        out = redact_access_path(raw)
        self.assertNotIn("supersecrettokenvalue123", out)
        self.assertIn("/integrations/soc/hooks/wazuh/<redacted>", out)


if __name__ == "__main__":
    unittest.main()
