"""KB-112 Step 2: Sovereign Edge unified portal RBAC policy tests."""

from __future__ import annotations

import unittest

from fastapi import HTTPException

from app.api.dependencies import require_roles
from app.services.sovereign_rbac import (
    CUSTOMER_DASHBOARD_ROLES,
    SOC_ENGINEER_ROLES,
    sovereign_customer_allowed_path,
    sovereign_customer_forbidden_path,
    sovereign_customer_may_write,
    sovereign_http_status_for_deny,
    sovereign_route_access,
)


class SovereignRbacPolicyTests(unittest.TestCase):
    def test_soc_engineer_roles_complete(self):
        self.assertIn("platform_admin", SOC_ENGINEER_ROLES)
        self.assertIn("soc_analyst", SOC_ENGINEER_ROLES)
        self.assertTrue(
            CUSTOMER_DASHBOARD_ROLES.isdisjoint(SOC_ENGINEER_ROLES),
            "customer and SOC roles must not overlap",
        )

    def test_customer_blocked_from_admin_paths(self):
        for path in (
            "/admin/tenants",
            "/admin/appliances",
            "/v1/admin/audit-logs",
            "/api/v1/admin/customers",
        ):
            self.assertTrue(sovereign_customer_forbidden_path(path), path)

    def test_customer_allowed_dashboard_paths(self):
        for path in (
            "/customer/dashboard/DEMO",
            "/customer/incidents/DEMO",
            "/customer/alerts/DEMO",
            "/health",
            "/auth/me",
        ):
            self.assertTrue(sovereign_customer_allowed_path(path), path)
            allowed, reason = sovereign_route_access("customer_admin", "GET", path)
            self.assertTrue(allowed, f"{path}: {reason}")

    def test_customer_cannot_read_admin_even_with_get(self):
        allowed, reason = sovereign_route_access("customer_viewer", "GET", "/admin/tenants")
        self.assertFalse(allowed)
        self.assertEqual(reason, "forbidden_admin_route")
        self.assertEqual(sovereign_http_status_for_deny(reason), 403)

    def test_customer_write_only_on_approval_routes(self):
        self.assertTrue(
            sovereign_customer_may_write("POST", "/customer/incidents/DEMO/isolation/approve")
        )
        self.assertFalse(
            sovereign_customer_may_write("POST", "/admin/tenants/tier-rollout")
        )
        allowed, reason = sovereign_route_access(
            "customer_admin",
            "POST",
            "/customer/incidents/ALPHA/isolation/approve",
        )
        self.assertTrue(allowed, reason)

    def test_customer_post_to_incidents_list_denied(self):
        allowed, reason = sovereign_route_access(
            "customer_admin",
            "POST",
            "/customer/incidents/DEMO",
        )
        self.assertFalse(allowed)
        self.assertEqual(reason, "customer_write_denied")

    def test_soc_engineer_full_access(self):
        for path in ("/admin/tenants", "/customer/incidents/DEMO", "/internal/cluster"):
            allowed, reason = sovereign_route_access("soc_manager", "POST", path)
            self.assertTrue(allowed, f"{path}: {reason}")


class SovereignRbacRequireRolesIntegrationTests(unittest.TestCase):
    def test_require_roles_blocks_customer_from_admin_dependency(self):
        dep = require_roles("platform_admin", "soc_manager", "soc_analyst")
        customer = {"role": "customer_admin", "status": "active", "tenant_id": "t1"}
        with self.assertRaises(HTTPException) as ctx:
            dep(current_user=customer)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_require_roles_allows_soc_engineer(self):
        dep = require_roles("platform_admin", "soc_manager", "soc_analyst")
        engineer = {"role": "soc_analyst", "status": "active", "tenant_id": None}
        self.assertEqual(dep(current_user=engineer)["role"], "soc_analyst")


if __name__ == "__main__":
    unittest.main()
