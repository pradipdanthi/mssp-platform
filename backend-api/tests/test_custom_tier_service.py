"""Unit tests for admin-only CUSTOM tier provisioning."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services.custom_tier_service import (
    entitlements_for_custom_selection,
    normalize_custom_catalog_keys,
    provision_custom_tier,
)
from app.services.capability_access_service import catalog_key_enabled_in_entitlements


class CustomTierCatalogKeyTests(unittest.TestCase):
    def test_normalize_dedupes_and_lowercases(self):
        keys = normalize_custom_catalog_keys(
            ["Vulnerability_Management", "vulnerability_management", "network_detection_response"]
        )
        self.assertEqual(
            keys,
            ["vulnerability_management", "network_detection_response"],
        )

    def test_normalize_ignores_unknown_keys(self):
        keys = normalize_custom_catalog_keys(["not_a_module", "cloud_identity_protection"])
        self.assertEqual(keys, ["cloud_identity_protection"])


class CustomTierEntitlementBundleTests(unittest.TestCase):
    def test_empty_selection_raises(self):
        with self.assertRaises(ValueError):
            entitlements_for_custom_selection([])

    def test_gold_modules_enable_flags(self):
        bundle = entitlements_for_custom_selection(
            ["cloud_identity_protection", "vulnerability_management"]
        )
        self.assertTrue(bundle["cloud_identity_protection_enabled"])
        self.assertTrue(bundle["greenbone_enabled"])
        self.assertFalse(bundle["zeek_enabled"])

    def test_unselected_modules_disabled(self):
        bundle = entitlements_for_custom_selection(["cloud_identity_protection"])
        self.assertFalse(bundle["greenbone_enabled"])
        self.assertFalse(bundle["velociraptor_enabled"])

    def test_catalog_key_mapping_matches_entitlements(self):
        bundle = entitlements_for_custom_selection(
            ["network_detection_response", "threat_intelligence"]
        )
        self.assertTrue(catalog_key_enabled_in_entitlements("network_detection_response", bundle))
        self.assertTrue(catalog_key_enabled_in_entitlements("threat_intelligence", bundle))
        self.assertFalse(catalog_key_enabled_in_entitlements("vulnerability_management", bundle))


class CustomTierProvisionTests(unittest.TestCase):
    @patch("app.services.custom_tier_service.fulfill_tenant_capabilities")
    @patch("app.services.custom_tier_service.upsert_tenant_entitlements")
    @patch("app.services.custom_tier_service.set_tenant_subscription_tier")
    def test_provision_sets_custom_without_bundle_sync(
        self, mock_set_tier, mock_upsert, mock_fulfill
    ):
        mock_fulfill.return_value = {"adapter_sync_ok": 2}

        result = provision_custom_tier(
            "tenant-1",
            catalog_keys=["cloud_identity_protection", "vulnerability_management"],
            actor_user_id="admin-1",
            order_number="PO-CUSTOM-1",
        )

        mock_set_tier.assert_called_once_with(
            "tenant-1",
            "CUSTOM",
            sync_entitlements=False,
            actor_user_id="admin-1",
        )
        mock_upsert.assert_called_once()
        mock_fulfill.assert_called_once()
        self.assertEqual(result["subscription_tier"], "CUSTOM")
        self.assertIn("cloud_identity_protection", result["selected_catalog_keys"])
        self.assertIn("vulnerability_management", result["selected_catalog_keys"])


if __name__ == "__main__":
    unittest.main()
