"""KB-112: NikTiar Sovereign Edge deployment mode helpers and fulfillment."""

from __future__ import annotations

import unittest

from app.services.capability_fulfillment_service import plan_capability_fulfillment
from app.services.customer_safe_labels import customer_service_delivery_label
from app.services.sovereign_edge import (
    SOVEREIGN_EDGE_MODE,
    cloud_fleet_visible,
    default_cloud_egress_enabled,
    is_sovereign_edge,
    offline_license_delivery,
    uses_local_appliance_stack,
)


class SovereignEdgeModeTests(unittest.TestCase):
    def test_sovereign_edge_constants(self):
        self.assertTrue(is_sovereign_edge("sovereign_edge"))
        self.assertTrue(is_sovereign_edge(" SOVEREIGN_EDGE "))
        self.assertFalse(is_sovereign_edge("on_prem_appliance"))

    def test_local_appliance_stack_includes_sovereign(self):
        self.assertTrue(uses_local_appliance_stack(SOVEREIGN_EDGE_MODE))
        self.assertTrue(uses_local_appliance_stack("on_prem_appliance"))
        self.assertFalse(uses_local_appliance_stack("cloud"))

    def test_cloud_fleet_not_visible_for_sovereign(self):
        self.assertFalse(cloud_fleet_visible(SOVEREIGN_EDGE_MODE))
        self.assertTrue(cloud_fleet_visible("on_prem_appliance"))

    def test_default_egress_off_for_sovereign(self):
        self.assertFalse(default_cloud_egress_enabled(SOVEREIGN_EDGE_MODE))
        self.assertTrue(default_cloud_egress_enabled("on_prem_appliance"))

    def test_offline_license_only_for_sovereign(self):
        self.assertTrue(offline_license_delivery(SOVEREIGN_EDGE_MODE))
        self.assertFalse(offline_license_delivery("hybrid"))

    def test_customer_delivery_label(self):
        label = customer_service_delivery_label(SOVEREIGN_EDGE_MODE)
        self.assertIn("Sovereign Edge", label)
        self.assertIn("no cloud telemetry", label.lower())


class SovereignEdgeFulfillmentTests(unittest.TestCase):
    def test_sovereign_skips_all_cloud_syncs(self):
        ctx = {
            "uses_appliance": True,
            "is_sovereign_edge": True,
            "deployment_mode": SOVEREIGN_EDGE_MODE,
            "found": True,
        }
        plans = plan_capability_fulfillment(
            "tenant-1",
            ["cloud_identity_protection", "security_automation"],
            ctx=ctx,
        )
        self.assertEqual(len(plans), 2)
        for plan in plans:
            self.assertFalse(plan["cloud_sync"])
            self.assertEqual(plan["skip_reason"], "sovereign_local_stack")
            self.assertTrue(plan["appliance_license"])

    def test_hybrid_appliance_still_syncs_non_engine_modules(self):
        ctx = {
            "uses_appliance": True,
            "is_sovereign_edge": False,
            "deployment_mode": "on_prem_appliance",
            "found": True,
        }
        plans = plan_capability_fulfillment(
            "tenant-1",
            ["cloud_identity_protection", "vulnerability_management"],
            ctx=ctx,
        )
        by_key = {p["catalog_key"]: p for p in plans}
        self.assertTrue(by_key["cloud_identity_protection"]["cloud_sync"])
        self.assertFalse(by_key["vulnerability_management"]["cloud_sync"])


if __name__ == "__main__":
    unittest.main()
