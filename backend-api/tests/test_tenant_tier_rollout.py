"""Tests for tenant entitlement fetch completeness and tier sync helpers."""

from __future__ import annotations

import inspect
import unittest

from app.api.routes.tenant_management import _build_service_readiness, _fetch_entitlements_row


class TenantEntitlementsFetchTests(unittest.TestCase):
    def test_service_readiness_includes_tier_specific_modules(self):
        readiness = _build_service_readiness(
            {
                "wazuh_siem": True,
                "thehive_mode": "full",
                "shuffle_mode": "standard",
                "greenbone_enabled": True,
                "zeek_enabled": True,
                "misp_enabled": True,
                "velociraptor_enabled": True,
                "continuous_compliance_enabled": True,
                "external_attack_surface_enabled": True,
                "cloud_identity_protection_enabled": True,
            },
            {},
        )
        self.assertEqual(readiness["continuous_compliance"], "queued")
        self.assertEqual(readiness["external_attack_surface"], "queued")
        self.assertEqual(readiness["cloud_identity_protection"], "queued")

    def test_fetch_entitlements_row_query_contains_new_columns(self):
        source = inspect.getsource(_fetch_entitlements_row)
        self.assertIn("continuous_compliance_enabled", source)
        self.assertIn("external_attack_surface_enabled", source)
        self.assertIn("cloud_identity_protection_enabled", source)


if __name__ == "__main__":
    unittest.main()
