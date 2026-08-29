"""Unit tests for on-appliance sovereign profile helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "kevantic-appliance" / "appliance"))

try:
    from sovereign.profile import default_profile  # noqa: E402
except ImportError:  # pragma: no cover - appliance tree not in API image
    default_profile = None  # type: ignore[assignment,misc]


class SovereignProfileDefaultsTests(unittest.TestCase):
    def setUp(self) -> None:
        if default_profile is None:
            self.skipTest("appliance sovereign module not on PYTHONPATH")

    def test_default_profile_airgapped(self):
        prof = default_profile()
        self.assertEqual(prof["profile"], "sovereign_edge")
        self.assertFalse(prof["cloud_egress_enabled"])
        self.assertTrue(prof["offline_license"])
        self.assertTrue(prof["airgap_enabled"])


class SovereignProfilePostureTests(unittest.TestCase):
    def setUp(self) -> None:
        if default_profile is None:
            self.skipTest("appliance sovereign module not on PYTHONPATH")

    @patch("sovereign.profile.subprocess.run")
    @patch("sovereign.profile._first_existing_unit")
    def test_apply_posture_stops_channeld(self, mock_unit, mock_run):
        from sovereign.profile import apply_sovereign_posture

        mock_unit.side_effect = ["junexis-critical-alert-forwarder.service", "junexis-channeld.service", None]
        mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "inactive", "stderr": ""})()

        with patch("sovereign.profile.save_profile", side_effect=lambda x: x):
            with patch("sovereign.profile.apply_airgap_firewall", return_value={"enabled": True}):
                result = apply_sovereign_posture(default_profile(), dry_run=True)

        self.assertTrue(result["ok"])
        actions = result["systemd_actions"]
        self.assertTrue(any(a.get("unit") == "junexis-channeld.service" for a in actions))


# Re-import RBAC parity for sovereign unified portal contract in same test module run.
try:
    sys.path.insert(0, str(ROOT / "backend-api"))
    from app.services.sovereign_rbac import sovereign_route_access as rbac_access  # noqa: E402

    class SovereignRbacParityTests(unittest.TestCase):
        def test_customer_admin_blocked_from_admin(self):
            allowed, reason = rbac_access("customer_admin", "GET", "/admin/tenants")
            self.assertFalse(allowed)
            self.assertEqual(reason, "forbidden_admin_route")

except ImportError:
    pass


if __name__ == "__main__":
    unittest.main()
