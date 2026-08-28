"""Tests for customer-safe delivery labels (U3 portal parity)."""

from __future__ import annotations

import unittest

from app.services.customer_safe_labels import customer_service_delivery_label


class CustomerServiceDeliveryLabelTests(unittest.TestCase):
    def test_appliance_modes_describe_local_logs(self):
        label = customer_service_delivery_label("on_prem_appliance")
        self.assertIn("Edge", label)
        self.assertIn("locally", label)

    def test_cloud_direct_matches_cloud_soc_wording(self):
        label = customer_service_delivery_label("on_prem_direct")
        self.assertIn("Cloud SOC", label)

    def test_hybrid_mentions_both_paths(self):
        label = customer_service_delivery_label("hybrid")
        self.assertIn("Hybrid", label)


if __name__ == "__main__":
    unittest.main()
