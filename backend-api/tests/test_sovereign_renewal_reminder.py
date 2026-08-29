"""KB-112 Step 4: Sovereign Edge renewal reminder tests."""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "kevantic-appliance" / "appliance"))

from sovereign.renewal_reminder import build_renewal_reminder  # noqa: E402


class SovereignRenewalReminderTests(unittest.TestCase):
    def test_no_expiry_inactive(self):
        payload = build_renewal_reminder(exp=None)
        self.assertFalse(payload["active"])
        self.assertIsNone(payload["message"])

    def test_far_future_inactive(self):
        exp = int(time.time()) + 400 * 86400
        payload = build_renewal_reminder(exp=exp)
        self.assertFalse(payload["active"])

    def test_within_30_days_warning(self):
        exp = int(time.time()) + 20 * 86400
        payload = build_renewal_reminder(exp=exp)
        self.assertTrue(payload["active"])
        self.assertIn("20 day", payload["message"])
        self.assertFalse(payload["customer_may_apply_license"])

    def test_expired_critical(self):
        exp = int(time.time()) - 86400
        payload = build_renewal_reminder(exp=exp)
        self.assertEqual(payload["level"], "expired")
        self.assertEqual(payload["action"], "contact_mssp_for_offline_renewal")


if __name__ == "__main__":
    unittest.main()
