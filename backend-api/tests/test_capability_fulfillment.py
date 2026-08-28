"""Tests for uniform capability fulfillment router."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services.capability_fulfillment_service import (
    CLOUD_ENGINE_SYNC_SKIPPED_ON_APPLIANCE,
    fulfill_tenant_capabilities,
    plan_capability_fulfillment,
    run_cloud_control_plane_syncs,
)


class CapabilityFulfillmentPlanTests(unittest.TestCase):
    def test_cloud_direct_runs_all_cloud_syncs(self):
        ctx = {"uses_appliance": False, "deployment_mode": "on_prem_direct", "found": True}
        keys = ["vulnerability_management", "external_attack_surface", "cloud_identity_protection"]
        plans = plan_capability_fulfillment("t1", keys, ctx=ctx)
        self.assertTrue(all(p["cloud_sync"] for p in plans))
        self.assertFalse(any(p["appliance_license"] for p in plans))

    def test_appliance_skips_local_engine_cloud_syncs(self):
        ctx = {"uses_appliance": True, "deployment_mode": "on_prem_appliance", "found": True}
        keys = [
            "vulnerability_management",
            "external_attack_surface",
            "cloud_identity_protection",
            "security_automation",
        ]
        plans = plan_capability_fulfillment("t1", keys, ctx=ctx)
        by_key = {p["catalog_key"]: p for p in plans}

        self.assertFalse(by_key["vulnerability_management"]["cloud_sync"])
        self.assertEqual(by_key["vulnerability_management"]["skip_reason"], "local_appliance_engine")
        self.assertEqual(by_key["vulnerability_management"]["appliance_svc_id"], "svc-04")

        self.assertFalse(by_key["external_attack_surface"]["cloud_sync"])
        self.assertTrue(by_key["cloud_identity_protection"]["cloud_sync"])
        self.assertTrue(by_key["security_automation"]["cloud_sync"])

    def test_skipped_keys_constant_covers_vm_easm_ndr_compliance_forensics(self):
        self.assertIn("vulnerability_management", CLOUD_ENGINE_SYNC_SKIPPED_ON_APPLIANCE)
        self.assertIn("external_attack_surface", CLOUD_ENGINE_SYNC_SKIPPED_ON_APPLIANCE)
        self.assertIn("network_detection_response", CLOUD_ENGINE_SYNC_SKIPPED_ON_APPLIANCE)


class CapabilityFulfillmentExecutionTests(unittest.TestCase):
    @patch("app.services.capability_fulfillment_service.trigger_post_enable_sync")
    def test_run_cloud_syncs_skips_appliance_local_engines(self, mock_sync):
        mock_sync.return_value = {"catalog_key": "x", "synced": True}
        ctx = {"uses_appliance": True, "deployment_mode": "on_prem_appliance", "found": True}
        results = run_cloud_control_plane_syncs(
            "t1",
            ["vulnerability_management", "cloud_identity_protection"],
            ctx=ctx,
        )
        mock_sync.assert_called_once_with("t1", "cloud_identity_protection")
        skipped = [r for r in results if r.get("skipped") == "local_appliance_engine"]
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["catalog_key"], "vulnerability_management")

    @patch("app.services.appliance_entitlement_sync.enqueue_tenant_entitlement_jobs")
    @patch("app.services.capability_fulfillment_service.run_cloud_control_plane_syncs")
    @patch("app.services.capability_fulfillment_service.get_tenant_fulfillment_context")
    def test_fulfill_tenant_capabilities_orchestrates_uniform_path(
        self, mock_ctx, mock_sync, mock_enqueue
    ):
        mock_ctx.return_value = {
            "tenant_id": "t1",
            "deployment_mode": "on_prem_appliance",
            "uses_appliance": True,
            "found": True,
        }
        mock_sync.return_value = [{"catalog_key": "cloud_identity_protection", "synced": True}]
        mock_enqueue.return_value = {"jobs_queued": 1, "appliances": 1}

        result = fulfill_tenant_capabilities(
            "t1",
            catalog_keys=["cloud_identity_protection", "vulnerability_management"],
            catalog_key_label="tier_gold",
            order_number="PO-1",
        )

        mock_sync.assert_called_once()
        mock_enqueue.assert_called_once()
        self.assertTrue(result["uses_appliance"])
        self.assertEqual(result["appliance_entitlement_push"]["jobs_queued"], 1)
        self.assertEqual(len(result["fulfillment_plan"]), 2)


if __name__ == "__main__":
    unittest.main()
