"""Occurrence merge: same host/rule/behaviour collapse; SLA and audit stay honest."""

from __future__ import annotations

import os
import unittest

from app.schemas.soc_sync import SocSyncRequest
from app.services.soc_alert_merge import (
    behaviour_key,
    extract_cve,
    higher_severity,
    merge_fingerprint,
)


def _payload(**overrides) -> SocSyncRequest:
    data = {
        "source_tool": "wazuh",
        "external_alert_id": "1793.1",
        "severity": "high",
        "alert_title": "Executable file dropped in folder commonly used by malware",
        "alert_description": "Wazuh rule 92213 level 15; agent=WIN-A",
        "destination_host": "WIN-BL72S84GDTF",
        "source_user": "Administrator",
        "technical_summary": (
            "Wazuh rule 92213 level 15; image=powershell.exe; "
            "target_file=C:\\Users\\ADMINI~1\\AppData\\Local\\Temp\\drop.exe; user=Administrator"
        ),
        "rule_id": "92213",
        "tenant_short_code": "ALPHAWINCORP-6VS2",
    }
    data.update(overrides)
    return SocSyncRequest(**data)


class FingerprintTests(unittest.TestCase):
    def test_same_host_rule_file_same_fingerprint(self):
        a = merge_fingerprint(_payload(external_alert_id="1"))
        b = merge_fingerprint(_payload(external_alert_id="2"))
        self.assertTrue(a)
        self.assertEqual(a, b)

    def test_different_cve_does_not_merge(self):
        a = merge_fingerprint(
            _payload(
                alert_title="CVE-2026-11111 affects Microsoft Windows Server 2022 Standard Evaluation",
                alert_description="Wazuh rule 23505 level 10",
                rule_id="23505",
                technical_summary="groups=vulnerability-detector",
            )
        )
        b = merge_fingerprint(
            _payload(
                external_alert_id="2",
                alert_title="CVE-2026-22222 affects Microsoft Windows Server 2022 Standard Evaluation",
                alert_description="Wazuh rule 23505 level 10",
                rule_id="23505",
                technical_summary="groups=vulnerability-detector",
            )
        )
        self.assertNotEqual(a, b)

    def test_different_host_does_not_merge(self):
        a = merge_fingerprint(_payload())
        b = merge_fingerprint(_payload(external_alert_id="2", destination_host="WIN-OTHER"))
        self.assertNotEqual(a, b)

    def test_different_file_is_different_behaviour(self):
        a = merge_fingerprint(_payload())
        b = merge_fingerprint(
            _payload(
                external_alert_id="2",
                technical_summary=(
                    "Wazuh rule 92213 level 15; image=powershell.exe; "
                    "target_file=C:\\Windows\\Temp\\other.exe; user=Administrator"
                ),
            )
        )
        self.assertNotEqual(a, b)
        self.assertIn("file:", behaviour_key(_payload()))

    def test_missing_host_refuses_merge(self):
        self.assertIsNone(merge_fingerprint(_payload(destination_host=None)))

    def test_cve_extracted_from_title(self):
        self.assertEqual(
            extract_cve("CVE-2026-69934 affects Microsoft Windows Server 2022"),
            "CVE-2026-69934",
        )

    def test_severity_only_rises(self):
        self.assertEqual(higher_severity("high", "critical"), "critical")
        self.assertEqual(higher_severity("critical", "medium"), "critical")


class OccurrenceDbTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if os.getenv("TIA_RUN_MERGE_DB_TESTS") != "1":
            raise unittest.SkipTest(
                "set TIA_RUN_MERGE_DB_TESTS=1 against a throwaway Postgres with migration 124"
            )
        import tia_testenv

        tia_testenv.require_database()
        from app.db.session import fetch_one

        row = fetch_one("SELECT to_regclass('public.security_alert_occurrences') AS t;")
        if not row or not row.get("t"):
            raise RuntimeError("migration 124 is not applied to the test database")

    def setUp(self) -> None:
        from app.db.session import execute

        self.tid = "aaaaaaaa-1111-2222-3333-44444444444a"
        execute(
            "INSERT INTO tenants (id, name, short_code) VALUES (%s::uuid, 'Merge T', 'MERG') "
            "ON CONFLICT DO NOTHING;",
            (self.tid,),
        )
        execute("DELETE FROM security_alerts WHERE tenant_id = %s::uuid;", (self.tid,))

    def tearDown(self) -> None:
        from app.db.session import execute

        execute("DELETE FROM security_alerts WHERE tenant_id = %s::uuid;", (self.tid,))

    def test_second_identical_event_merges_and_keeps_first_seen(self):
        from app.services.soc_sync_service import sync_soc_alert
        from app.db.session import fetch_one

        first = sync_soc_alert(_payload(external_alert_id="occ-1", tenant_short_code="MERG"))
        before = fetch_one(
            "SELECT first_seen_at, created_at FROM security_alerts WHERE id = %s::uuid;",
            (first[0]["alert_id"],),
        )
        second = sync_soc_alert(_payload(external_alert_id="occ-2", tenant_short_code="MERG"))
        self.assertEqual(first[0]["alert_id"], second[0]["alert_id"])
        self.assertTrue(second[0]["merged"])
        self.assertTrue(second[1])
        self.assertEqual(int(second[0]["occurrence_count"]), 2)
        row = fetch_one(
            "SELECT occurrence_count, first_seen_at, created_at, last_seen_at FROM security_alerts WHERE id = %s::uuid;",
            (first[0]["alert_id"],),
        )
        self.assertEqual(int(row["occurrence_count"]), 2)
        self.assertEqual(row["first_seen_at"], before["first_seen_at"])
        self.assertEqual(row["created_at"], before["created_at"])
        n = fetch_one(
            "SELECT count(*)::int AS n FROM security_alert_occurrences WHERE alert_id = %s::uuid;",
            (first[0]["alert_id"],),
        )
        self.assertEqual(int(n["n"]), 2)
        audit = fetch_one(
            "SELECT count(*)::int AS n FROM audit_logs WHERE entity_id = %s::uuid AND action = 'alert_occurrence_merged';",
            (first[0]["alert_id"],),
        )
        self.assertGreaterEqual(int(audit["n"]), 1)

    def test_closed_parent_opens_a_new_alert_with_new_sla_clock(self):
        from app.services.soc_sync_service import sync_soc_alert
        from app.db.session import execute, fetch_one

        first, _ = sync_soc_alert(_payload(external_alert_id="cls-1", tenant_short_code="MERG"))
        execute(
            "UPDATE security_alerts SET status = 'closed' WHERE id = %s::uuid;",
            (first["alert_id"],),
        )
        second, dup = sync_soc_alert(_payload(external_alert_id="cls-2", tenant_short_code="MERG"))
        self.assertFalse(dup)
        self.assertFalse(second.get("merged"))
        self.assertNotEqual(first["alert_id"], second["alert_id"])
        row = fetch_one(
            "SELECT recurrence_of_alert_id::text AS parent, occurrence_count FROM security_alerts WHERE id = %s::uuid;",
            (second["alert_id"],),
        )
        self.assertEqual(row["parent"], first["alert_id"])
        self.assertEqual(int(row["occurrence_count"]), 1)


if __name__ == "__main__":
    unittest.main()
