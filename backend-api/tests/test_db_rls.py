"""Phase 2: RLS tenant isolation and retention purge integration tests."""

from __future__ import annotations

import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone

from app.db.session import (
    SOC_BYPASS_ROLES,
    execute,
    fetch_all,
    fetch_one,
    reset_db_session_context,
    set_db_session_context,
)

TENANT_A = "aaaaaaaa-1111-2222-3333-444444444441"
TENANT_B = "aaaaaaaa-1111-2222-3333-444444444442"
MARKER = "rls-phase2-test"


def _postgres_available() -> bool:
    try:
        row = fetch_one("SELECT 1 AS ok;")
        return bool(row.get("ok"))
    except Exception:
        return False


def _migrations_applied() -> bool:
    try:
        from app.db.session import _get_pool

        with _get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 AS ok FROM pg_proc "
                    "WHERE proname = 'purge_expired_tenant_data' LIMIT 1"
                )
                fn = cur.fetchone()
                cur.execute(
                    "SELECT relrowsecurity AS rls_enabled FROM pg_class "
                    "WHERE relname = 'security_alerts' LIMIT 1"
                )
                rls = cur.fetchone()
                cur.execute(
                    "SELECT 1 AS ok FROM pg_roles WHERE rolname = 'mssp_app' LIMIT 1"
                )
                role = cur.fetchone()
        return bool(fn) and bool(rls and rls.get("rls_enabled")) and bool(role)
    except Exception:
        return False


def _ensure_test_tenants() -> None:
    for tid, code in ((TENANT_A, "RLSTSTA"), (TENANT_B, "RLSTSTB")):
        execute(
            """
            INSERT INTO tenants (id, short_code, name, status)
            VALUES (%s::uuid, %s, %s, 'active')
            ON CONFLICT (id) DO NOTHING;
            """,
            (tid, code, f"RLS Test {code}"),
        )


def _delete_test_tenants() -> None:
    """Remove lab-only RLS fixtures; never leave RLSTSTA/RLSTSTB in admin tenant lists."""
    execute(
        """
        DELETE FROM tenants
        WHERE id IN (%s::uuid, %s::uuid);
        """,
        (TENANT_A, TENANT_B),
    )


def _insert_marker_alert(tenant_id: str, suffix: str) -> str:
    alert_id = str(uuid.uuid4())
    execute(
        """
        INSERT INTO security_alerts (
            id, tenant_id, source_tool, external_alert_id,
            severity, alert_title, alert_description, status
        ) VALUES (
            %s::uuid, %s::uuid, 'wazuh', %s,
            'low', %s, %s, 'new'
        );
        """,
        (
            alert_id,
            tenant_id,
            f"{MARKER}-{suffix}",
            f"{MARKER} title {suffix}",
            f"{MARKER} description {suffix}",
        ),
    )
    return alert_id

def _delete_marker_alerts() -> None:
    execute(
        """
        DELETE FROM security_alerts
        WHERE external_alert_id LIKE %s;
        """,
        (f"{MARKER}%",),
    )


@unittest.skipUnless(_postgres_available(), "Postgres not available")
@unittest.skipUnless(_migrations_applied(), "Migrations 041/042 not applied")
class RlsTenantIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_test_tenants()
        _delete_marker_alerts()
        cls.alert_a = _insert_marker_alert(TENANT_A, "a")
        cls.alert_b = _insert_marker_alert(TENANT_B, "b")

    @classmethod
    def tearDownClass(cls):
        _delete_marker_alerts()
        _delete_test_tenants()

    def test_rls_blocks_cross_tenant_reads(self):
        tokens = set_db_session_context(tenant_id=TENANT_A, role="customer_admin")
        try:
            guc = fetch_one(
                """
                SELECT
                    current_setting('app.current_tenant', true) AS tenant,
                    current_setting('app.current_role', true) AS role,
                    current_user AS db_user
                """
            )
            self.assertEqual(guc.get("tenant"), TENANT_A)
            rows = fetch_all(
                """
                SELECT id::text
                FROM security_alerts
                WHERE external_alert_id IN (%s, %s)
                """,
                (f"{MARKER}-a", f"{MARKER}-b"),
            )
        finally:
            reset_db_session_context(tokens)

        ids = {row["id"] for row in rows}
        self.assertIn(self.alert_a, ids)
        self.assertNotIn(self.alert_b, ids)
    def test_soc_role_bypasses_rls(self):
        for role in SOC_BYPASS_ROLES:
            with self.subTest(role=role):
                tokens = set_db_session_context(tenant_id=TENANT_A, role=role)
                try:
                    rows = fetch_all(
                        """
                        SELECT id::text
                        FROM security_alerts
                        WHERE external_alert_id IN (%s, %s)
                        """,
                        (f"{MARKER}-a", f"{MARKER}-b"),
                    )
                finally:
                    reset_db_session_context(tokens)
                ids = {row["id"] for row in rows}
                self.assertIn(self.alert_a, ids)
                self.assertIn(self.alert_b, ids)


@unittest.skipUnless(_postgres_available(), "Postgres not available")
@unittest.skipUnless(_migrations_applied(), "Migrations 041/042 not applied")
class RetentionPurgeTests(unittest.TestCase):
    def test_purge_expired_tenant_data_runs_without_error(self):
        purge_marker = f"{MARKER}-purge-{uuid.uuid4().hex[:8]}"
        old_time = datetime.now(timezone.utc) - timedelta(days=120)
        _ensure_test_tenants()
        execute(
            """
            INSERT INTO security_alerts (
                tenant_id, source_tool, external_alert_id,
                severity, alert_title, status, created_at
            ) VALUES (
                %s::uuid, 'wazuh', %s,
                'low', %s, 'closed', %s
            );
            """,
            (TENANT_A, purge_marker, f"{MARKER} purge row", old_time),
        )
        try:
            rows = fetch_all("SELECT * FROM purge_expired_tenant_data(90);")
            table_names = {row["table_name"] for row in rows}
            self.assertIn("security_alerts", table_names)
            self.assertIn("audit_logs", table_names)
            self.assertIn("tenant_ndr_events", table_names)
            gone = fetch_one(
                "SELECT 1 AS ok FROM security_alerts WHERE external_alert_id = %s;",
                (purge_marker,),
            )
            self.assertFalse(gone)
        finally:
            execute(
                "DELETE FROM security_alerts WHERE external_alert_id = %s;",
                (purge_marker,),
            )
            _delete_test_tenants()


class RlsHelperUnitTests(unittest.TestCase):
    def test_soc_bypass_roles_defined(self):
        self.assertIn("soc_analyst", SOC_BYPASS_ROLES)
        self.assertIn("platform_admin", SOC_BYPASS_ROLES)


if __name__ == "__main__":
    unittest.main()
