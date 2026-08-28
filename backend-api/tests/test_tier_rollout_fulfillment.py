"""Tests for tier rollout fulfillment (Phase 0)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.services.tier_rollout_service import (
    catalog_keys_for_tier,
    fulfill_tier_change,
    fulfill_tier_rollout,
    newly_unlocked_catalog_keys,
)
from app.services.capability_fulfillment_service import (
    is_tier_downgrade,
    revoked_catalog_keys,
)


class TierRolloutCatalogKeyTests(unittest.TestCase):
    def test_silver_includes_cloud_identity_only(self):
        keys = catalog_keys_for_tier("SILVER")
        self.assertIn("cloud_identity_protection", keys)
        self.assertNotIn("security_automation", keys)
        self.assertNotIn("continuous_compliance", keys)

    def test_gold_adds_mdr_modules(self):
        keys = catalog_keys_for_tier("GOLD")
        self.assertIn("security_automation", keys)
        self.assertIn("vulnerability_management", keys)
        self.assertNotIn("threat_intelligence", keys)

    def test_platinum_includes_all_sync_modules(self):
        keys = catalog_keys_for_tier("PLATINUM")
        self.assertIn("continuous_compliance", keys)
        self.assertIn("network_detection_response", keys)
        self.assertIn("threat_intelligence", keys)

    def test_newly_unlocked_silver_to_gold(self):
        keys = newly_unlocked_catalog_keys("SILVER", "GOLD")
        self.assertIn("security_automation", keys)
        self.assertNotIn("cloud_identity_protection", keys)

    def test_revoked_platinum_to_gold(self):
        keys = revoked_catalog_keys("PLATINUM", "GOLD")
        self.assertIn("continuous_compliance", keys)
        self.assertIn("network_detection_response", keys)
        self.assertNotIn("vulnerability_management", keys)

    def test_is_tier_downgrade(self):
        self.assertTrue(is_tier_downgrade("PLATINUM", "GOLD"))
        self.assertFalse(is_tier_downgrade("GOLD", "PLATINUM"))


class TierRolloutFulfillmentTests(unittest.TestCase):
    @patch("app.services.tier_rollout_service.fulfill_tier_capabilities")
    def test_fulfill_tier_rollout_delegates_to_uniform_router(self, mock_fulfill):
        mock_fulfill.return_value = {
            "target_tier": "GOLD",
            "previous_tier": "SILVER",
            "coverage_rows_cleared": 2,
            "adapter_sync_ok": 1,
            "appliance_entitlement_push": {"jobs_queued": 1},
        }

        result = fulfill_tier_rollout(
            "tenant-uuid",
            target_tier="GOLD",
            previous_tier="SILVER",
            actor_user_id="admin-1",
            order_number="PO-100",
        )

        mock_fulfill.assert_called_once_with(
            "tenant-uuid",
            target_tier="GOLD",
            previous_tier="SILVER",
            actor_user_id="admin-1",
            order_number="PO-100",
            clear_asset_coverage=True,
        )
        self.assertEqual(result["target_tier"], "GOLD")

    @patch("app.services.tier_rollout_service.fulfill_tier_downgrade")
    def test_fulfill_tier_change_routes_downgrade(self, mock_downgrade):
        mock_downgrade.return_value = {"downgrade": True, "revoked_catalog_keys": ["zeek"]}
        result = fulfill_tier_change(
            "tenant-uuid",
            target_tier="GOLD",
            previous_tier="PLATINUM",
            order_number="PO-200",
        )
        mock_downgrade.assert_called_once()
        self.assertTrue(result["downgrade"])

    @patch("app.services.appliance_entitlement_sync.enqueue_tenant_entitlement_jobs")
    @patch("app.services.capability_fulfillment_service.fetch_one")
    def test_push_skips_cloud_direct_tenants(self, mock_fetch, mock_enqueue):
        mock_fetch.return_value = {
            "id": "t1",
            "deployment_mode": "on_prem_direct",
            "subscription_tier": "SILVER",
        }

        from app.services.capability_fulfillment_service import push_appliance_license

        result = push_appliance_license("t1", catalog_key="tier_gold")

        self.assertEqual(result["skipped"], "not_appliance_deployment")
        mock_enqueue.assert_not_called()

    @patch("app.services.appliance_entitlement_sync.enqueue_tenant_entitlement_jobs")
    @patch("app.services.capability_fulfillment_service.fetch_one")
    def test_push_queues_jobs_for_appliance_tenants(self, mock_fetch, mock_enqueue):
        mock_fetch.return_value = {
            "id": "t1",
            "deployment_mode": "on_prem_appliance",
            "subscription_tier": "PLATINUM",
        }
        mock_enqueue.return_value = {"jobs_queued": 2, "appliances": 1}

        from app.services.capability_fulfillment_service import push_appliance_license

        result = push_appliance_license(
            "t1",
            catalog_key="tier_platinum",
            actor_user_id="admin-1",
            order_number="SO-9",
        )

        mock_enqueue.assert_called_once_with(
            tenant_id="t1",
            catalog_key="tier_platinum",
            action="enable",
            actor_user_id="admin-1",
            order_number="SO-9",
        )
        self.assertEqual(result["jobs_queued"], 2)


if __name__ == "__main__":
    unittest.main()
