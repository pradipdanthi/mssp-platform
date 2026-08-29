"""KB-114 Step 6: Sovereign full stack + unified portal tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "kevantic-appliance" / "appliance"))
sys.path.insert(0, str(ROOT / "backend-api"))

from sovereign import full_stack, rbac as appliance_rbac  # noqa: E402
from app.services import sovereign_rbac as backend_rbac  # noqa: E402


class SovereignFullStackManifestTests(unittest.TestCase):
    def test_default_manifest(self):
        manifest = full_stack.default_manifest(mode="stub")
        self.assertEqual(manifest["profile"], "sovereign_full_stack")
        self.assertEqual(manifest["mode"], "stub")
        self.assertEqual(manifest["thehive_port"], 9000)

    @patch("sovereign.full_stack._docker_available", return_value=False)
    @patch("sovereign.full_stack._mem_total_mb", return_value=4096)
    def test_recommend_stub_on_small_appliance(self, _mem, _docker):
        self.assertEqual(full_stack.recommend_mode(), "stub")

    @patch("sovereign.full_stack._docker_available", return_value=True)
    @patch("sovereign.full_stack._mem_total_mb", return_value=16384)
    def test_recommend_docker_when_capable(self, _mem, _docker):
        self.assertEqual(full_stack.recommend_mode(), "docker")


class SovereignRbacParityTests(unittest.TestCase):
    def test_customer_admin_blocked_from_admin(self):
        allowed, reason = appliance_rbac.sovereign_route_access("customer_admin", "GET", "/admin/tenants")
        self.assertFalse(allowed)
        self.assertEqual(reason, "forbidden_admin_route")
        backend_allowed, backend_reason = backend_rbac.sovereign_route_access(
            "customer_admin", "GET", "/admin/tenants"
        )
        self.assertEqual((allowed, reason), (backend_allowed, backend_reason))

    def test_customer_proxy_blocked(self):
        allowed, _ = appliance_rbac.sovereign_route_access("customer_viewer", "GET", "/proxy/thehive/")
        self.assertFalse(allowed)

    def test_soc_engineer_admin_allowed(self):
        allowed, reason = appliance_rbac.sovereign_route_access("soc_analyst", "GET", "/admin/tenants")
        self.assertTrue(allowed)
        self.assertIsNone(reason)


if __name__ == "__main__":
    unittest.main()
