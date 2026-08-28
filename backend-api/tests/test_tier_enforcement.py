"""Unit tests for subscription tier enforcement."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.api.middleware.tier_enforcement import enforce_tenant_subscription_tier
from app.api.v1.identity_ingest import ingest_okta_telemetry
from app.api.routes.compliance import customer_compliance_summary
from app.api.routes.ndr import customer_ndr_summary
from app.api.routes.vmaas import customer_vmaas_summary
from app.services.subscription_tier_service import (
    DEMO_TENANT_SHORT_CODES,
    SubscriptionTier,
    entitlements_for_tier,
    is_demo_tenant,
    tier_meets_minimum,
)
from app.services.tenant_entitlement_defaults import (
    DEMO_FULL_ENTITLEMENTS,
    is_demo_full_entitlement_tenant,
)

TENANT_SILVER = "aaaaaaaa-1111-2222-3333-444444444441"
TENANT_GOLD = "bbbbbbbb-2222-3333-4444-555555555552"
TENANT_PLATINUM = "cccccccc-3333-4444-5555-666666666663"
TENANT_CUSTOM = "dddddddd-4444-5555-6666-777777777774"


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
        self.assertEqual(platinum["greenbone_cadence"], "daily")


class DemoTenantConfigTests(unittest.TestCase):
    def test_demo_short_code_is_centralized(self):
        self.assertIn("ALPHAWINCORP-6VS2", DEMO_TENANT_SHORT_CODES)
        self.assertTrue(is_demo_tenant("alphawincorp-6vs2"))
        self.assertTrue(is_demo_full_entitlement_tenant("ALPHAWINCORP-6VS2"))

    def test_demo_entitlements_match_platinum_bundle(self):
        platinum = entitlements_for_tier("PLATINUM")
        demo = DEMO_FULL_ENTITLEMENTS
        for key, value in platinum.items():
            if key == "roadmap_notes":
                continue
            self.assertEqual(demo[key], value)


class VmaasCustomerTierTests(unittest.TestCase):
    @patch("app.api.routes.vmaas.require_tenant_match")
    @patch("app.api.routes.vmaas.vmaas.get_summary", return_value={})
    @patch("app.api.routes.vmaas.enforce_tenant_subscription_tier")
    @patch(
        "app.api.routes.vmaas._resolve_tenant",
        return_value={"id": TENANT_SILVER, "short_code": "SILV1", "name": "Silver"},
    )
    def test_silver_tenant_vmaas_forbidden(self, _mock_resolve, mock_enforce, _mock_summary, _mock_match):
        mock_enforce.side_effect = HTTPException(
            status_code=403,
            detail="This capability requires a GOLD or PLATINUM subscription tier.",
        )
        user = {"role": "customer_admin", "tenant_id": TENANT_SILVER}
        with self.assertRaises(HTTPException) as ctx:
            customer_vmaas_summary("SILV1", current_user=user)
        self.assertEqual(ctx.exception.status_code, 403)

    @patch("app.api.routes.vmaas.require_tenant_match")
    @patch("app.api.routes.vmaas.vmaas.get_summary", return_value={"open_findings": 0})
    @patch("app.api.routes.vmaas.enforce_tenant_subscription_tier")
    @patch(
        "app.api.routes.vmaas._resolve_tenant",
        return_value={"id": TENANT_GOLD, "short_code": "GOLD1", "name": "Gold"},
    )
    def test_gold_tenant_vmaas_allowed(self, _mock_resolve, mock_enforce, _mock_summary, _mock_match):
        user = {"role": "customer_admin", "tenant_id": TENANT_GOLD}
        result = customer_vmaas_summary("GOLD1", current_user=user)
        mock_enforce.assert_called_once_with(
            TENANT_GOLD, SubscriptionTier.GOLD, catalog_key="vulnerability_management"
        )
        self.assertEqual(result["tenant"]["short_code"], "GOLD1")


class ComplianceCustomerTierTests(unittest.TestCase):
    @patch("app.api.routes.compliance.require_tenant_match")
    @patch("app.api.routes.compliance.sca.get_summary", return_value={"overall_score_percentage": 0})
    @patch("app.api.routes.compliance.sca.maybe_refresh_tenant")
    @patch("app.api.routes.compliance.enforce_tenant_subscription_tier")
    @patch(
        "app.api.routes.compliance._resolve_tenant",
        return_value={"id": TENANT_GOLD, "short_code": "GOLD1", "name": "Gold"},
    )
    def test_gold_tenant_compliance_forbidden(self, _mock_resolve, mock_enforce, _mock_refresh, _mock_summary, _mock_match):
        mock_enforce.side_effect = HTTPException(
            status_code=403,
            detail="This capability requires a PLATINUM subscription tier.",
        )
        user = {"role": "customer_admin", "tenant_id": TENANT_GOLD}
        with self.assertRaises(HTTPException) as ctx:
            customer_compliance_summary("GOLD1", current_user=user)
        self.assertEqual(ctx.exception.status_code, 403)


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
        mock_enforce.assert_called_once_with(
            TENANT_SILVER, SubscriptionTier.SILVER, catalog_key="cloud_identity_protection"
        )
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
        mock_enforce.assert_called_once_with(
            TENANT_PLATINUM, SubscriptionTier.PLATINUM, catalog_key="network_detection_response"
        )
        self.assertEqual(result["tenant"]["short_code"], "PLAT1")


class CustomTierEnforcementTests(unittest.TestCase):
    @patch("app.api.middleware.tier_enforcement.get_tenant_subscription_tier", return_value="CUSTOM")
    @patch(
        "app.api.middleware.tier_enforcement.tenant_has_capability_for_min_tier",
        return_value=False,
    )
    def test_custom_without_flag_forbidden(self, _mock_has, _mock_tier):
        with self.assertRaises(HTTPException) as ctx:
            enforce_tenant_subscription_tier(
                TENANT_CUSTOM,
                SubscriptionTier.GOLD,
                catalog_key="vulnerability_management",
            )
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("custom subscription", str(ctx.exception.detail).lower())

    @patch("app.api.middleware.tier_enforcement.get_tenant_subscription_tier", return_value="CUSTOM")
    @patch(
        "app.api.middleware.tier_enforcement.tenant_has_capability_for_min_tier",
        return_value=True,
    )
    def test_custom_with_flag_allowed(self, _mock_has, _mock_tier):
        enforce_tenant_subscription_tier(
            TENANT_CUSTOM,
            SubscriptionTier.GOLD,
            catalog_key="vulnerability_management",
        )


class PlatinumAccessTests(unittest.TestCase):
    @patch("app.api.middleware.tier_enforcement.get_tenant_subscription_tier", return_value="PLATINUM")
    def test_platinum_passes_all_tier_checks(self, _mock_tier):
        for min_tier in (SubscriptionTier.SILVER, SubscriptionTier.GOLD, SubscriptionTier.PLATINUM):
            enforce_tenant_subscription_tier(TENANT_PLATINUM, min_tier)


if __name__ == "__main__":
    unittest.main()
