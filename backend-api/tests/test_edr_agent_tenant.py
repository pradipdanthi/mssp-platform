"""P0: EDR agent_id tenant ownership guards."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services.edr_actions import (
    assert_agent_tenant_access,
    validate_agent_tenant_ownership,
)

TENANT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
BINDING_ROW = {"wazuh_agent_group": "tenant_TENANTA", "short_code": "TENANTA"}


class ValidateAgentTenantOwnershipTests(unittest.TestCase):
    @patch("app.services.edr_actions.fetch_one")
    def test_returns_false_for_empty_inputs(self, mock_fetch):
        self.assertFalse(validate_agent_tenant_ownership("", "001"))
        self.assertFalse(validate_agent_tenant_ownership(TENANT_ID, ""))
        self.assertFalse(validate_agent_tenant_ownership(TENANT_ID, "bad id!"))
        mock_fetch.assert_not_called()

    @patch("app.services.edr_actions.fetch_one")
    def test_true_when_protected_asset_matches(self, mock_fetch):
        mock_fetch.return_value = {"?column?": 1}
        self.assertTrue(validate_agent_tenant_ownership(TENANT_ID, "042"))
        mock_fetch.assert_called_once()

    @patch("app.services.edr_actions.fetch_one")
    def test_true_when_alert_history_matches(self, mock_fetch):
        mock_fetch.side_effect = [None, {"?column?": 1}]
        self.assertTrue(validate_agent_tenant_ownership(TENANT_ID, "042"))
        self.assertEqual(mock_fetch.call_count, 2)

    @patch("app.services.edr_actions.wazuh_client.get_agent_groups", return_value=[])
    @patch("app.services.edr_actions.wazuh_client.credentials_configured", return_value=True)
    @patch("app.services.edr_actions.fetch_one")
    def test_false_when_no_tier_matches(
        self, mock_fetch, _mock_creds, _mock_groups
    ):
        mock_fetch.side_effect = [None, None, BINDING_ROW]
        self.assertFalse(validate_agent_tenant_ownership(TENANT_ID, "042"))
        self.assertEqual(mock_fetch.call_count, 3)

    @patch(
        "app.services.edr_actions.wazuh_client.get_agent_groups",
        return_value=["tenant_TENANTA"],
    )
    @patch("app.services.edr_actions.wazuh_client.credentials_configured", return_value=True)
    @patch("app.services.edr_actions.fetch_one")
    def test_true_for_new_agent_in_tenant_wazuh_group_only(
        self, mock_fetch, _mock_creds, mock_groups
    ):
        """New agent: no protected_assets, no alerts, but correct Wazuh group."""
        mock_fetch.side_effect = [None, None, BINDING_ROW]
        self.assertTrue(validate_agent_tenant_ownership(TENANT_ID, "042"))
        mock_groups.assert_called_once_with("042")
        self.assertEqual(mock_fetch.call_count, 3)

    @patch(
        "app.services.edr_actions.wazuh_client.get_agent_groups",
        return_value=["tenant_TENANTB"],
    )
    @patch("app.services.edr_actions.wazuh_client.credentials_configured", return_value=True)
    @patch("app.services.edr_actions.fetch_one")
    def test_false_when_agent_in_other_tenant_wazuh_group(
        self, mock_fetch, _mock_creds, _mock_groups
    ):
        """Cross-tenant: agent belongs to Tenant B group, not Tenant A."""
        mock_fetch.side_effect = [None, None, BINDING_ROW]
        self.assertFalse(validate_agent_tenant_ownership(TENANT_ID, "042"))


class AssertAgentTenantAccessTests(unittest.TestCase):
    def test_soc_roles_bypass_ownership_check(self):
        user = {"role": "soc_analyst", "tenant_id": "tenant-a"}
        assert_agent_tenant_access(
            user,
            tenant_id="tenant-b",
            agent_id="999",
        )

    @patch("app.services.edr_actions.validate_agent_tenant_ownership", return_value=True)
    def test_customer_allowed_when_owner(self, _mock_validate):
        user = {"role": "customer_admin", "tenant_id": "tenant-a"}
        assert_agent_tenant_access(
            user,
            tenant_id="tenant-a",
            agent_id="042",
        )

    @patch("app.services.edr_actions.validate_agent_tenant_ownership", return_value=False)
    def test_customer_denied_cross_tenant_agent(self, _mock_validate):
        user = {"role": "customer_admin", "tenant_id": "tenant-a"}
        with self.assertRaises(PermissionError) as ctx:
            assert_agent_tenant_access(
                user,
                tenant_id="tenant-a",
                agent_id="999",
            )
        self.assertIn("Access denied", str(ctx.exception))

    @patch(
        "app.services.edr_actions.wazuh_client.get_agent_groups",
        return_value=["tenant_TENANTA"],
    )
    @patch("app.services.edr_actions.wazuh_client.credentials_configured", return_value=True)
    @patch("app.services.edr_actions.fetch_one")
    def test_customer_admin_allowed_via_wazuh_group_tier(
        self, mock_fetch, _mock_creds, _mock_groups
    ):
        user = {"role": "customer_admin", "tenant_id": TENANT_ID}
        mock_fetch.side_effect = [None, None, BINDING_ROW]
        assert_agent_tenant_access(
            user,
            tenant_id=TENANT_ID,
            agent_id="042",
        )

    def test_empty_agent_id_is_noop(self):
        user = {"role": "customer_admin", "tenant_id": "tenant-a"}
        assert_agent_tenant_access(user, tenant_id="tenant-a", agent_id=None)
        assert_agent_tenant_access(user, tenant_id="tenant-a", agent_id="  ")


class ExecuteEdrActionIdorTests(unittest.TestCase):
    @patch("app.services.edr_actions._insert_execution", return_value="exec-1")
    @patch("app.services.edr_actions._resolve_incident", return_value=None)
    @patch("app.services.edr_actions._resolve_tenant")
    @patch("app.services.edr_actions.validate_agent_tenant_ownership", return_value=False)
    def test_customer_cross_tenant_agent_raises_permission_error(
        self,
        _mock_validate,
        mock_resolve_tenant,
        _mock_incident,
        _mock_insert,
    ):
        from app.schemas.edr import EdrActionExecuteRequest
        from app.services.edr_actions import execute_edr_action

        mock_resolve_tenant.return_value = {"id": "tenant-a", "short_code": "TENANTA"}
        user = {"id": "user-1", "role": "customer_admin", "tenant_id": "tenant-a"}
        body = EdrActionExecuteRequest(
            action_type="ISOLATE_HOST",
            tenant_short_code="TENANTA",
            agent_id="999",
            confirm_isolation=True,
        )
        with self.assertRaises(PermissionError):
            execute_edr_action(user, body)

    @patch("app.services.edr_actions.validate_agent_tenant_ownership", return_value=False)
    @patch("app.services.edr_actions._resolve_tenant")
    def test_soc_staff_not_blocked_by_ownership_check(
        self,
        mock_resolve_tenant,
        _mock_validate,
    ):
        from app.services.edr_actions import assert_agent_tenant_access

        mock_resolve_tenant.return_value = {"id": "tenant-b", "short_code": "TENANTB"}
        user = {"id": "soc-1", "role": "soc_analyst", "tenant_id": None}
        assert_agent_tenant_access(
            user,
            tenant_id="tenant-b",
            agent_id="999",
        )


if __name__ == "__main__":
    unittest.main()
