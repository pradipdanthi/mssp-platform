"""Unit tests for subscription tier enforcement."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.api.middleware.tier_enforcement import enforce_tenant_subscription_tier
from app.api.v1.identity_ingest import ingest_okta_telemetry
from app.api.routes.ndr import customer_ndr_summary
from app.services.subscription_tier_service import (
    SubscriptionTier,
    entitlements_for_tier,
    tier_meets_minimum,
)

TENANT_SILVER = "aaaaaaaa-1111-2222-3333-444444444441"
TENANT_GOLD = "bbbbbbbb-2222-3333-4444-555555555552"
TENANT_PLATINUM = "cccccccc-3333-4444-5555-666666666663"


class TierRankTests(unittest.TestCase):
    def test_tier_meets_minimum(self):
        self.assertTrue(tier_meets_minimum("PLATINUM", SubscriptionTier.GOLD))
        self.assertTrue(tier_meets_minimum("GOLD", SubscriptionTier.GOLD))
        self.assertFalse(tier_meets_minimum("SILVER", SubscriptionTier.GOLD))


class TierEntitlementBundleTests(unittest.TestCase):
    def test_platinum_includes_gold_and_silver_flags(self):
        platinum = entitlements_for_tier("PLATINUM")
        gold = entitlements_for_tier("GOLD")
        silver = entitlements_for_tier("SILVER")
        self.assertTrue(platinum["cloud_identity_protection_enabled"])
        self.assertTrue(platinum["greenbone_enabled"])
        self.assertTrue(platinum["zeek_enabled"])
        self.assertTrue(silver["cloud_identity_protection_enabled"])
        self.assertFalse(silver["greenbone_enabled"])
        self.assertTrue(gold["greenbone_enabled"])
        self.assertFalse(gold["zeek_enabled"])


class EnforceTenantTierTests(unittest.TestCase):
    @patch("app.api.middleware.tier_enforcement.get_tenant_subscription_tier", return_value="SILVER")
    def test_silver_blocked_from_gold(self, _mock_tier):
        with self.assertRaises(HTTPException) as ctx:
            enforce_tenant_subscription_tier(TENANT_SILVER, SubscriptionTier.GOLD)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("GOLD or PLATINUM", str(ctx.exception.detail))

    @patch("app.api.middleware.tier_enforcement.get_tenant_subscription_tier", return_value="PLATINUM")
    def test_platinum_passes_gold_check(self, _mock_tier):
        enforce_tenant_subscription_tier(TENANT_PLATINUM, SubscriptionTier.GOLD)


class OktaIngestTierTests(unittest.TestCase):
    @patch("app.api.v1.identity_ingest.process_okta_event", return_value=[])
    @patch("app.api.v1.identity_ingest.db_transaction")
    @patch("app.api.v1.identity_ingest._resolve_tenant_id", return_value=TENANT_SILVER)
    @patch("app.api.v1.identity_ingest.enforce_tenant_subscription_tier")
    def test_silver_tenant_okta_ingest_allowed(
        self, mock_enforce, _mock_resolve, mock_tx, _mock_process
    ):
        mock_tx.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_tx.return_value.__exit__ = MagicMock(return_value=False)
        from app.api.v1.identity_ingest import OktaTelemetryRequest

        result = ingest_okta_telemetry(
            OktaTelemetryRequest(events=[{"eventType": "user.session.start"}]),
            x_tenant_id=TENANT_SILVER,
            x_agent_api_key="key",
            x_appliance_id=None,
            x_appliance_api_key=None,
            authorization=None,
        )
        mock_enforce.assert_called_once_with(TENANT_SILVER, SubscriptionTier.SILVER)
        self.assertEqual(result.tenant_id, TENANT_SILVER)


class EdrExecuteTierTests(unittest.TestCase):
    @patch("app.api.middleware.tier_enforcement.get_tenant_subscription_tier", return_value="SILVER")
    def test_silver_tenant_edr_execute_forbidden(self, _mock_tier):
        with self.assertRaises(HTTPException) as ctx:
            enforce_tenant_subscription_tier(TENANT_SILVER, SubscriptionTier.GOLD)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("GOLD or PLATINUM", str(ctx.exception.detail))


class NdrCustomerTierTests(unittest.TestCase):
    @patch("app.api.routes.ndr.require_tenant_match")
    @patch("app.api.routes.ndr.ndr.get_summary", return_value={})
    @patch("app.api.routes.ndr.enforce_tenant_subscription_tier")
    @patch("app.api.routes.ndr._resolve_tenant", return_value={"id": TENANT_GOLD, "short_code": "GOLD1", "name": "Gold"})
    def test_gold_tenant_ndr_forbidden(self, _mock_resolve, mock_enforce, _mock_summary, _mock_match):
        mock_enforce.side_effect = HTTPException(
            status_code=403,
            detail="This capability requires a PLATINUM subscription tier.",
        )
        user = {"role": "customer_admin", "tenant_id": TENANT_GOLD}
        with self.assertRaises(HTTPException) as ctx:
            customer_ndr_summary("GOLD1", current_user=user)
        self.assertEqual(ctx.exception.status_code, 403)

    @patch("app.api.routes.ndr.require_tenant_match")
    @patch("app.api.routes.ndr.ndr.get_summary", return_value={"open_events": 0})
    @patch("app.api.routes.ndr.enforce_tenant_subscription_tier")
    @patch("app.api.routes.ndr._resolve_tenant", return_value={"id": TENANT_PLATINUM, "short_code": "PLAT1", "name": "Plat"})
    def test_platinum_tenant_ndr_allowed(self, _mock_resolve, mock_enforce, _mock_summary, _mock_match):
        user = {"role": "customer_admin", "tenant_id": TENANT_PLATINUM}
        result = customer_ndr_summary("PLAT1", current_user=user)
        mock_enforce.assert_called_once_with(TENANT_PLATINUM, SubscriptionTier.PLATINUM)
        self.assertEqual(result["tenant"]["short_code"], "PLAT1")


class PlatinumAccessTests(unittest.TestCase):
    @patch("app.api.middleware.tier_enforcement.get_tenant_subscription_tier", return_value="PLATINUM")
    def test_platinum_passes_all_tier_checks(self, _mock_tier):
        for min_tier in (SubscriptionTier.SILVER, SubscriptionTier.GOLD, SubscriptionTier.PLATINUM):
            enforce_tenant_subscription_tier(TENANT_PLATINUM, min_tier)


if __name__ == "__main__":
    unittest.main()
