"""Phase 6: identity telemetry ingest and threat detection."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.services.identity_threat_engine import (
    IdentityDetection,
    clear_event_store,
    detect_kerberoasting,
    detect_mfa_fatigue,
    emit_identity_alert,
    process_ad_event,
    process_okta_event,
)

TENANT_A = "aaaaaaaa-1111-2222-3333-444444444441"
TENANT_B = "bbbbbbbb-2222-3333-4444-555555555552"
BASE_TIME = datetime(2026, 8, 28, 12, 0, 0, tzinfo=timezone.utc)


def _okta_event(
    *,
    event_type: str,
    outcome: str,
    user: str = "alice@example.com",
    ip: str = "203.0.113.10",
    offset_seconds: int = 0,
    event_uuid: str = "evt-1",
) -> dict:
    return {
        "uuid": event_uuid,
        "published": (BASE_TIME + timedelta(seconds=offset_seconds)).isoformat(),
        "eventType": event_type,
        "outcome": {"result": outcome},
        "actor": {"alternateId": user},
        "client": {"ipAddress": ip},
        "geographicalContext": {"country": "US", "city": "New York"},
    }


class MfaFatigueDetectionTests(unittest.TestCase):
    def setUp(self):
        clear_event_store()

    def tearDown(self):
        clear_event_store()

    def test_mfa_fatigue_triggers_after_four_failures_then_success(self):
        for i in range(4):
            process_okta_event(
                TENANT_A,
                _okta_event(
                    event_type="user.authentication.auth_via_mfa",
                    outcome="FAILURE",
                    offset_seconds=i * 30,
                    event_uuid=f"fail-{i}",
                ),
            )

        with patch(
            "app.services.identity_threat_engine.emit_identity_alert",
            return_value="alert-mfa-1",
        ) as mock_emit:
            alert_ids = process_okta_event(
                TENANT_A,
                _okta_event(
                    event_type="user.authentication.auth_via_mfa",
                    outcome="SUCCESS",
                    offset_seconds=150,
                    event_uuid="success-1",
                ),
            )

        self.assertEqual(alert_ids, ["alert-mfa-1"])
        mock_emit.assert_called_once()
        detection = mock_emit.call_args[0][1]
        self.assertEqual(detection.detection_type, "mfa_fatigue")
        self.assertEqual(detection.source_tool, "okta")
        self.assertEqual(detection.severity, "high")

    def test_mfa_fatigue_does_not_trigger_with_only_three_failures(self):
        for i in range(3):
            process_okta_event(
                TENANT_A,
                _okta_event(
                    event_type="user.mfa.factor.verify",
                    outcome="FAILURE",
                    offset_seconds=i * 20,
                    event_uuid=f"fail-{i}",
                ),
            )
        with patch(
            "app.services.identity_threat_engine.emit_identity_alert",
        ) as mock_emit:
            alert_ids = process_okta_event(
                TENANT_A,
                _okta_event(
                    event_type="user.authentication.auth_via_mfa",
                    outcome="SUCCESS",
                    offset_seconds=90,
                    event_uuid="success-1",
                ),
            )
        self.assertEqual(alert_ids, [])
        mock_emit.assert_not_called()

    def test_detect_mfa_fatigue_unit(self):
        clear_event_store()
        user = "bob@example.com"
        for i in range(4):
            process_okta_event(
                TENANT_A,
                _okta_event(
                    event_type="user.mfa.factor.challenge",
                    outcome="DENY",
                    user=user,
                    offset_seconds=i * 10,
                    event_uuid=f"f-{i}",
                ),
            )
        det = detect_mfa_fatigue(
            TENANT_A,
            user,
            current_outcome="SUCCESS",
            current_event_id="user.authentication.auth_via_mfa",
            current_time=BASE_TIME + timedelta(minutes=2),
        )
        self.assertIsNotNone(det)
        self.assertGreater(len(det.event_ids), 3)


class KerberoastingDetectionTests(unittest.TestCase):
    def test_kerberoasting_on_4769_rc4_non_machine_account(self):
        event = {
            "EventID": 4769,
            "TimeCreated": BASE_TIME.isoformat(),
            "TargetUserName": "svc_sql",
            "ServiceName": "MSSQLSvc/db01.example.com",
            "TicketEncryptionType": "0x17",
            "IpAddress": "10.20.30.40",
            "SubjectUserName": "attacker@CORP",
        }
        det = detect_kerberoasting(event)
        self.assertIsNotNone(det)
        self.assertEqual(det.detection_type, "kerberoasting")
        self.assertEqual(det.source_tool, "active_directory")
        self.assertEqual(det.severity, "critical")
        self.assertIn("4769", det.event_ids)
        self.assertIn("RC4", det.risk_indicators[0])

    def test_kerberoasting_ignored_for_machine_account(self):
        event = {
            "EventID": 4769,
            "TargetUserName": "WIN-DC01$",
            "ServiceName": "krbtgt/CORP.LOCAL",
            "TicketEncryptionType": "0x17",
        }
        self.assertIsNone(detect_kerberoasting(event))

    @patch("app.services.identity_threat_engine.emit_identity_alert", return_value="alert-krb-1")
    def test_process_ad_event_emits_kerberoasting_alert(self, mock_emit):
        event = {
            "EventID": 4769,
            "TimeCreated": BASE_TIME.isoformat(),
            "TargetUserName": "app_svc",
            "ServiceName": "HTTP/web.internal",
            "TicketEncryptionType": "0x17",
            "IpAddress": "192.168.1.50",
        }
        alert_ids = process_ad_event(TENANT_A, event)
        self.assertEqual(alert_ids, ["alert-krb-1"])
        mock_emit.assert_called_once()
        self.assertEqual(mock_emit.call_args[0][0], TENANT_A)


class TenantIsolationTests(unittest.TestCase):
    def setUp(self):
        clear_event_store()

    def tearDown(self):
        clear_event_store()

    @patch("app.services.identity_threat_engine.emit_identity_alert")
    def test_tenant_a_events_never_emit_for_tenant_b(self, mock_emit):
        mock_emit.return_value = "alert-a"

        for i in range(4):
            process_okta_event(
                TENANT_A,
                _okta_event(
                    event_type="user.authentication.auth_via_mfa",
                    outcome="FAILURE",
                    user="alice@tenant-a.com",
                    offset_seconds=i * 15,
                    event_uuid=f"a-fail-{i}",
                ),
            )

        # Tenant B success must not inherit Tenant A failure window.
        mock_emit.reset_mock()
        alert_ids_b = process_okta_event(
            TENANT_B,
            _okta_event(
                event_type="user.authentication.auth_via_mfa",
                outcome="SUCCESS",
                user="alice@tenant-a.com",
                offset_seconds=90,
                event_uuid="b-success-only",
            ),
        )
        self.assertEqual(alert_ids_b, [])
        mock_emit.assert_not_called()

        alert_ids_a = process_okta_event(
            TENANT_A,
            _okta_event(
                event_type="user.authentication.auth_via_mfa",
                outcome="SUCCESS",
                user="alice@tenant-a.com",
                offset_seconds=90,
                event_uuid="a-success",
            ),
        )
        self.assertEqual(alert_ids_a, ["alert-a"])
        self.assertEqual(mock_emit.call_args_list[-1][0][0], TENANT_A)


class EmitIdentityAlertTests(unittest.TestCase):
    def test_emit_writes_security_alerts_row(self):
        detection = IdentityDetection(
            detection_type="kerberoasting",
            source_tool="active_directory",
            severity="critical",
            subject_user="svc@corp",
            target_ip="10.0.0.5",
            event_ids=["4769"],
            risk_indicators=["RC4 TGS"],
            details={"service_name": "HTTP/app"},
        )
        cur = MagicMock()
        cur.fetchone.side_effect = [None, {"id": "new-alert-id"}]
        alert_id = emit_identity_alert(TENANT_A, detection, cur=cur)
        self.assertEqual(alert_id, "new-alert-id")
        insert_sql = cur.execute.call_args_list[-1][0][0]
        self.assertIn("INSERT INTO security_alerts", insert_sql)
        params = cur.execute.call_args_list[-1][0][1]
        self.assertEqual(params[0], TENANT_A)
        self.assertEqual(params[1], "active_directory")
        self.assertEqual(params[3], "critical")


class IdentityIngestAuthTests(unittest.TestCase):
    @patch("app.api.v1.identity_ingest.fetch_one", return_value={"id": TENANT_A})
    @patch(
        "app.api.v1.identity_ingest.configured_identity_api_key",
        return_value="test-agent-key",
    )
    def test_resolve_tenant_with_bearer_and_x_tenant_id(self, _mock_key, _mock_tenant):
        from app.api.v1.identity_ingest import _resolve_tenant_id

        tenant_id = _resolve_tenant_id(
            x_tenant_id=TENANT_A,
            x_appliance_id=None,
            x_appliance_api_key=None,
            authorization="Bearer test-agent-key",
            x_agent_api_key=None,
        )
        self.assertEqual(tenant_id, TENANT_A)

    @patch(
        "app.api.v1.identity_ingest.configured_identity_api_key",
        return_value="test-agent-key",
    )
    def test_invalid_bearer_rejected(self, _mock_key):
        from fastapi import HTTPException

        from app.api.v1.identity_ingest import _resolve_tenant_id

        with self.assertRaises(HTTPException) as ctx:
            _resolve_tenant_id(
                x_tenant_id=TENANT_A,
                x_appliance_id=None,
                x_appliance_api_key=None,
                authorization="Bearer wrong-key",
                x_agent_api_key=None,
            )
        self.assertEqual(ctx.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
