"""Acceptance gate, increment 2: unified result acceptance, review lifecycle, outbox.

LOCAL tests only. They need a Postgres initialised from postgres/init (including
117 and 118) and skip otherwise. They use a recording transport; no real contact
is ever messaged and no network call is made. They are not staging verification.
"""

from __future__ import annotations

import json
import os
import unittest
import uuid
from unittest.mock import patch

import test_tia_failure_path as base
import tia_testenv
from app.services import tia_acceptance as acc
from app.services import tia_outbox, tia_schema
from app.services.tia_outbox import Receipt, TransportError


class FakeTransport:
    """Records sends. ``fail_times`` raises that many transient errors first."""

    def __init__(self, fail_times: int = 0, permanent: bool = False) -> None:
        self.sent = []
        self.ids = []
        self.fail_times = fail_times
        self.permanent = permanent

    def __call__(self, channel: str, recipient: str, message: str) -> Receipt:
        if self.fail_times > 0:
            self.fail_times -= 1
            raise TransportError("synthetic transport failure", permanent=self.permanent)
        message_id = f"wamid.{uuid.uuid4().hex}"
        self.sent.append((channel, recipient, message))
        self.ids.append(message_id)
        return Receipt(provider="test-transport", message_id=message_id)


ROSTER = "+15550001111"
ESCALATION = "+15550009999"

OFFICER = {"id": None, "email": "manager@example.test", "role": "soc_manager"}
ANALYST = {"id": None, "email": "analyst@example.test", "role": "soc_analyst"}
ANALYST2 = {"id": None, "email": "analyst2@example.test", "role": "soc_analyst"}
ADMIN = {"id": None, "email": "admin@example.test", "role": "platform_admin"}
CUSTOMER = {"id": None, "email": "cust@example.test", "role": "customer_admin"}


class AcceptanceBase(unittest.TestCase):
    TENANT_A = "cccccccc-1111-2222-3333-444444444441"
    TENANT_B = "cccccccc-1111-2222-3333-444444444442"

    @classmethod
    def setUpClass(cls) -> None:
        tia_testenv.require_database()
        from app.db.session import execute

        for tid, code in ((cls.TENANT_A, "TIAACC1"), (cls.TENANT_B, "TIAACC2")):
            execute(
                "INSERT INTO tenants (id, name, short_code) VALUES (%s::uuid, %s, %s) ON CONFLICT DO NOTHING;",
                (tid, f"TIA acceptance {code}", code),
            )

    @classmethod
    def tearDownClass(cls) -> None:
        from app.db.session import execute

        for tid in (cls.TENANT_A, cls.TENANT_B):
            execute("DELETE FROM tenants WHERE id = %s::uuid;", (tid,))

    def setUp(self) -> None:
        tia_schema.reset_cache()
        self.addCleanup(tia_schema.reset_cache)
        env = patch.dict(
            os.environ,
            {"SOC_ONCALL_WHATSAPP": ROSTER, "SOC_ONCALL_ESCALATION_WHATSAPP": "", "TIA_NOTIFY_MAX_ATTEMPTS": "4"},
        )
        env.start()
        self.addCleanup(env.stop)
        self.transport = FakeTransport()
        tia_outbox.set_transport(self.transport)
        self.addCleanup(tia_outbox.set_transport, None)

    # -- helpers ---------------------------------------------------------
    def alert(self, severity="critical", tenant=None, description=None) -> str:
        from app.db.session import execute

        alert_id = str(uuid.uuid4())
        execute(
            """
            INSERT INTO security_alerts (id, tenant_id, source_tool, external_alert_id, severity, alert_title,
                                         alert_description, event_time, status)
            VALUES (%s::uuid, %s::uuid, 'wazuh', %s, %s, 'synthetic', %s, now(), 'new');
            """,
            (alert_id, tenant or self.TENANT_A, f"ext-{alert_id}", severity, description),
        )
        return alert_id

    def attempt(self, alert_id: str, tenant=None) -> dict:
        return acc.open_attempt(alert_id=alert_id, tenant_id=tenant or self.TENANT_A)

    def accept(self, att: dict, raw, source="http", **claims):
        return acc.accept_result(source=source, attempt_id=att["attempt_id"], raw=raw, **claims)

    def one(self, sql, params=()):
        from app.db.session import fetch_one

        return fetch_one(sql, params)

    def all(self, sql, params=()):
        from app.db.session import fetch_all

        return fetch_all(sql, params)

    def execute(self, sql, params=()):
        from app.db.session import execute

        execute(sql, params)

    def pages(self, alert_id: str, kind="page"):
        return self.all(
            "SELECT * FROM tia_notifications WHERE alert_id = %s::uuid AND kind = %s ORDER BY created_at;",
            (alert_id, kind),
        )

    def item(self, alert_id: str):
        row = self.one("SELECT * FROM tia_review_items WHERE alert_id = %s::uuid ORDER BY first_seen_at DESC LIMIT 1;", (alert_id,))
        if not row:
            return None
        return {**row, "id": str(row["id"])}

    def events(self, item_id: str):
        return [r["event_type"] for r in self.all("SELECT event_type FROM tia_review_events WHERE review_item_id = %s::uuid ORDER BY created_at, id;", (item_id,))]

    def results(self, alert_id: str):
        return self.all("SELECT * FROM tia_results WHERE alert_id = %s::uuid ORDER BY accepted_at;", (alert_id,))

    def critical_success(self, **over):
        return base.v2_success(verdict="Critical", confidence=over.pop("confidence", 90), **over)

    def make_due(self, alert_id: str) -> None:
        self.execute(
            "UPDATE tia_notifications SET next_attempt_at = now() - interval '1 second' WHERE alert_id = %s::uuid;",
            (alert_id,),
        )


class ResultAcceptanceTests(AcceptanceBase):
    def test_http_first_then_callback_is_a_duplicate(self) -> None:
        a = self.alert("critical")
        att = self.attempt(a)
        raw = self.critical_success()
        first = self.accept(att, raw, source="http")
        second = self.accept(att, raw, source="callback")
        self.assertEqual((first.status, first.applied), ("accepted", True))
        self.assertEqual(second.status, "duplicate")
        self.assertEqual(len(self.results(a)), 1)
        self.assertEqual(len(self.pages(a)), 1)
        self.assertEqual(self.events(self.item(a)["id"]), ["created"])
        decisions = [r["decision"] for r in self.all("SELECT decision FROM tia_acceptance_log WHERE attempt_id = %s::uuid ORDER BY created_at, id;", (att["attempt_id"],))]
        self.assertEqual(decisions, ["accepted", "duplicate"])

    def test_callback_first_then_http_is_a_duplicate(self) -> None:
        a = self.alert("critical")
        att = self.attempt(a)
        raw = self.critical_success()
        first = self.accept(att, raw, source="callback")
        second = self.accept(att, raw, source="http")
        self.assertEqual((first.status, second.status), ("accepted", "duplicate"))
        self.assertEqual(len(self.results(a)), 1)
        self.assertEqual(len(self.pages(a)), 1)
        self.assertEqual(self.results(a)[0]["first_source"], "callback")

    def test_the_real_callback_body_shape_is_accepted_as_the_same_result(self) -> None:
        from app.api.routes.soc_agent_callback import TriageResultIn

        a = self.alert("high")
        att = self.attempt(a)
        raw = base.v2_success(verdict="Suspicious", confidence=70)
        self.accept(att, raw, source="http")
        body = TriageResultIn(alert_id=a, attempt_id=att["attempt_id"], tenant_id=self.TENANT_A, **{k: raw[k] for k in ("ok", "contract", "execution", "llm")})
        again = acc.accept_result(
            source="callback", attempt_id=body.attempt_id, claimed_tenant_id=body.tenant_id,
            claimed_alert_id=body.alert_id, raw=body.model_dump(),
        )
        self.assertEqual(again.status, "duplicate")

    def test_duplicate_delivery_of_a_failure_makes_no_second_transition(self) -> None:
        a = self.alert("critical")
        att = self.attempt(a)
        for _ in range(3):
            self.accept(att, base.v2_failure("failed", "auth_failure"))
        item = self.item(a)
        self.assertEqual(item["occurrences"], 1)
        self.assertEqual(self.events(item["id"]), ["created"])
        self.assertEqual(len(self.pages(a)), 1)
        self.assertEqual(len(self.results(a)), 1)

    def test_conflicting_payload_for_the_same_result_is_rejected_not_overwritten(self) -> None:
        a = self.alert("high")
        att = self.attempt(a)
        first = self.accept(att, base.v2_success(verdict="Suspicious", confidence=70))
        conflict = self.accept(att, self.critical_success(), source="callback")
        self.assertEqual(first.status, "accepted")
        self.assertEqual(conflict.status, "conflict")
        row = self.results(a)[0]
        self.assertEqual(row["verdict"], "SUSPICIOUS")
        self.assertEqual(self.one("SELECT ai_verdict FROM security_alerts WHERE id = %s::uuid;", (a,))["ai_verdict"], "SUSPICIOUS")
        log = self.one("SELECT count(*)::int AS n FROM tia_acceptance_log WHERE attempt_id = %s::uuid AND decision = 'conflict';", (att["attempt_id"],))
        self.assertEqual(log["n"], 1)

    def test_result_row_is_immutable(self) -> None:
        a = self.alert("high")
        self.accept(self.attempt(a), base.v2_success())
        with self.assertRaises(Exception):
            self.execute("UPDATE tia_results SET verdict = 'MALICIOUS' WHERE alert_id = %s::uuid;", (a,))

    def test_tenant_job_and_evidence_mismatches_are_rejected(self) -> None:
        a = self.alert("high")
        other = self.alert("high", tenant=self.TENANT_B)
        att = self.attempt(a)
        cases = {
            "tenant_mismatch": {"claimed_tenant_id": self.TENANT_B},
            "alert_mismatch": {"claimed_alert_id": other},
            "job_mismatch": {"claimed_job_id": f"{a}:wrong"},
            "evidence_version_mismatch": {"claimed_evidence_version": "not-the-version"},
        }
        for reason, claims in cases.items():
            with self.subTest(reason):
                res = self.accept(att, base.v2_success(), **claims)
                self.assertEqual((res.status, res.reason), ("rejected", reason))
        self.assertEqual(self.results(a), [])
        self.assertEqual(self.one("SELECT status FROM tia_investigation_attempts WHERE id = %s::uuid;", (att["attempt_id"],))["status"], "dispatched")
        self.assertIsNone(self.one("SELECT ai_verdict FROM security_alerts WHERE id = %s::uuid;", (a,))["ai_verdict"])
        self.assertEqual(self.accept({"attempt_id": str(uuid.uuid4())}, base.v2_success()).reason, "unknown_attempt")
        self.assertEqual(self.accept({"attempt_id": "not-a-uuid"}, base.v2_success()).reason, "invalid_attempt_id")
        rejected = self.one("SELECT count(*)::int AS n FROM tia_acceptance_log WHERE decision = 'rejected' AND alert_id = %s::uuid;", (a,))
        self.assertEqual(rejected["n"], 4)

    def test_a_result_after_the_window_is_rejected(self) -> None:
        a = self.alert("high")
        att = self.attempt(a)
        self.execute("UPDATE tia_investigation_attempts SET accept_until = now() - interval '1 second' WHERE id = %s::uuid;", (att["attempt_id"],))
        res = self.accept(att, base.v2_success())
        self.assertEqual(res.reason, "attempt_window_expired")

    def test_failure_in_the_transaction_rolls_everything_back(self) -> None:
        a = self.alert("critical")
        att = self.attempt(a)
        with patch.object(acc, "_enqueue_page", side_effect=RuntimeError("database went away")):
            with self.assertRaises(RuntimeError):
                self.accept(att, base.v2_failure("failed", "auth_failure"))
        self.assertEqual(self.results(a), [])
        self.assertIsNone(self.item(a))
        self.assertEqual(self.pages(a), [])
        self.assertEqual(self.one("SELECT status FROM tia_investigation_attempts WHERE id = %s::uuid;", (att["attempt_id"],))["status"], "dispatched")
        # the same work, retried, now succeeds exactly once
        self.assertEqual(self.accept(att, base.v2_failure("failed", "auth_failure")).status, "accepted")
        self.assertEqual(len(self.results(a)), 1)
        self.assertEqual(len(self.pages(a)), 1)


class TimeoutAndLateResultTests(AcceptanceBase):
    def test_http_timeout_then_late_critical_callback_pages_and_keeps_history(self) -> None:
        a = self.alert("critical")
        att = self.attempt(a)
        failed = acc.record_attempt_failure(attempt_id=att["attempt_id"], category="timeout", timed_out=True, error="client_timeout")
        self.assertEqual(failed.status, "accepted")
        item = self.item(a)
        self.assertEqual(item["reason_code"], "investigation_timed_out")
        self.assertIn("uncertainty", json.dumps(item["limited_evidence"]))
        attempt = self.one("SELECT status, outcome_uncertain FROM tia_investigation_attempts WHERE id = %s::uuid;", (att["attempt_id"],))
        self.assertEqual((attempt["status"], attempt["outcome_uncertain"]), ("timed_out", True))
        self.assertEqual(len(self.pages(a)), 1)  # "analysis unavailable" page

        late = self.accept(att, self.critical_success(), source="callback")
        self.assertEqual((late.status, late.late, late.applied), ("accepted", True, True))
        self.assertEqual(self.one("SELECT ai_verdict FROM security_alerts WHERE id = %s::uuid;", (a,))["ai_verdict"], "MALICIOUS")
        pages = self.pages(a)
        self.assertEqual(len(pages), 2, "the late critical finding must trigger its own notification")
        self.assertTrue(any("MALICIOUS" in p["message_body"] for p in pages))
        item = self.item(a)
        self.assertEqual(item["status"], "open", "a late result never resolves the review obligation")
        self.assertEqual(self.events(item["id"])[0], "created")
        history = self.one("SELECT detail FROM tia_review_events WHERE review_item_id = %s::uuid ORDER BY created_at LIMIT 1;", (item["id"],))
        self.assertEqual(history["detail"]["execution_status"], "timed_out")
        attempt = self.one("SELECT status, outcome_uncertain, transport_error FROM tia_investigation_attempts WHERE id = %s::uuid;", (att["attempt_id"],))
        self.assertEqual((attempt["status"], attempt["outcome_uncertain"], attempt["transport_error"]), ("result_received", False, "client_timeout"))
        self.assertTrue(self.results(a)[0]["late"])

    def test_timeout_after_the_result_already_arrived_changes_nothing(self) -> None:
        a = self.alert("high")
        att = self.attempt(a)
        self.accept(att, base.v2_success(), source="callback")
        res = acc.record_attempt_failure(attempt_id=att["attempt_id"], category="timeout", timed_out=True)
        self.assertEqual(res.status, "duplicate")
        self.assertIsNone(self.item(a))

    def test_duplicate_critical_results_from_two_attempts_page_once(self) -> None:
        a = self.alert("critical")
        for _ in range(2):
            self.accept(self.attempt(a), self.critical_success())
        self.assertEqual(len(self.pages(a)), 1)
        self.assertEqual(len(self.results(a)), 2)

    def test_increased_priority_produces_its_own_escalation(self) -> None:
        a = self.alert("medium")
        self.accept(self.attempt(a), base.v2_failure("failed", "malformed_output"))
        self.assertEqual(self.pages(a), [])
        self.assertEqual(self.item(a)["assessed_priority"], "P3")
        res = self.accept(self.attempt(a), self.critical_success())
        self.assertEqual(res.review_action, "priority_raised")
        item = self.item(a)
        self.assertEqual((item["assessed_priority"], item["notify_urgency"]), ("P2", "page"))
        self.assertEqual(len(self.pages(a)), 1)

    def test_new_critical_evidence_is_not_treated_as_a_duplicate(self) -> None:
        a = self.alert("critical")
        first = self.attempt(a)
        self.accept(first, self.critical_success())
        self.execute("UPDATE security_alerts SET alert_description = 'new evidence arrived' WHERE id = %s::uuid;", (a,))
        second = self.attempt(a)
        self.assertNotEqual(first["evidence_version"], second["evidence_version"])
        self.accept(second, self.critical_success())
        self.assertEqual(len(self.pages(a)), 2)

    def test_a_different_kind_of_finding_is_not_a_duplicate_of_an_earlier_page(self) -> None:
        a = self.alert("critical")
        self.accept(self.attempt(a), base.v2_failure("failed", "auth_failure"))
        self.accept(self.attempt(a), self.critical_success())
        self.accept(self.attempt(a), self.critical_success())
        self.assertEqual(len(self.pages(a)), 2)

    def test_older_attempt_cannot_overwrite_a_newer_finding(self) -> None:
        a = self.alert("high")
        older, newer = self.attempt(a), self.attempt(a)
        applied = self.accept(newer, base.v2_success(verdict="Suspicious", confidence=70))
        self.assertTrue(applied.applied)
        late = self.accept(older, self.critical_success(confidence=95), source="callback")
        self.assertEqual((late.status, late.applied, late.reason), ("accepted", False, "superseded_by_newer_attempt"))
        self.assertTrue(late.material)
        self.assertEqual(self.one("SELECT ai_verdict FROM security_alerts WHERE id = %s::uuid;", (a,))["ai_verdict"], "SUSPICIOUS")
        self.assertIsNotNone(self.item(a), "a material finding is surfaced to a person without overwriting current state")
        self.assertEqual(len(self.pages(a)), 1)
        self.assertEqual(len(self.results(a)), 2, "the older finding is kept in history")

    def test_an_older_non_material_result_is_history_only(self) -> None:
        a = self.alert("high")
        older, newer = self.attempt(a), self.attempt(a)
        self.accept(newer, base.v2_success(verdict="Suspicious", confidence=70))
        late = self.accept(older, base.v2_success(verdict="Benign", confidence=95), source="callback")
        self.assertEqual((late.applied, late.review_action), (False, "history_only"))
        self.assertIsNone(self.item(a))
        self.assertEqual(self.one("SELECT ai_verdict FROM security_alerts WHERE id = %s::uuid;", (a,))["ai_verdict"], "SUSPICIOUS")

    def test_a_human_decision_is_never_overwritten(self) -> None:
        for label, sql in (
            ("accepted triage", "UPDATE security_alerts SET ai_triage_status = 'accepted', ai_verdict = 'BENIGN_FALSE_POSITIVE' WHERE id = %s::uuid;"),
            ("closed case", "UPDATE security_alerts SET status = 'closed' WHERE id = %s::uuid;"),
        ):
            with self.subTest(label):
                a = self.alert("critical")
                att = self.attempt(a)
                self.execute(sql, (a,))
                before = self.one("SELECT status, ai_verdict, ai_triage_status FROM security_alerts WHERE id = %s::uuid;", (a,))
                res = self.accept(att, self.critical_success(), source="callback")
                self.assertEqual((res.applied, res.reason, res.material), (False, "human_decision", True))
                self.assertEqual(self.one("SELECT status, ai_verdict, ai_triage_status FROM security_alerts WHERE id = %s::uuid;", (a,)), before)
                self.assertIsNotNone(self.item(a))
                self.assertEqual(len(self.pages(a)), 1)

    def test_stale_evidence_result_is_history_but_critical_is_surfaced(self) -> None:
        a = self.alert("critical")
        att = self.attempt(a)
        self.execute("UPDATE security_alerts SET alert_description = 'changed after dispatch' WHERE id = %s::uuid;", (a,))
        res = self.accept(att, self.critical_success())
        self.assertEqual((res.applied, res.reason, res.material), (False, "stale_evidence", True))
        self.assertIsNone(self.one("SELECT ai_verdict FROM security_alerts WHERE id = %s::uuid;", (a,))["ai_verdict"])
        self.assertEqual(len(self.pages(a)), 1)

    def test_stale_attempts_with_no_result_become_uncertain_timeouts(self) -> None:
        a = self.alert("high")
        att = self.attempt(a)
        self.execute("UPDATE tia_investigation_attempts SET dispatched_at = now() - interval '1 day' WHERE id = %s::uuid;", (att["attempt_id"],))
        self.assertGreaterEqual(tia_outbox.reconcile_stale_attempts(), 1)
        attempt = self.one("SELECT status, outcome_uncertain FROM tia_investigation_attempts WHERE id = %s::uuid;", (att["attempt_id"],))
        self.assertEqual((attempt["status"], attempt["outcome_uncertain"]), ("timed_out", True))
        self.assertEqual(self.item(a)["reason_code"], "investigation_timed_out")


class ReviewLifecycleTests(AcceptanceBase):
    def test_retries_do_not_reset_age_or_extend_the_deadline(self) -> None:
        a = self.alert("medium")
        self.accept(self.attempt(a), base.v2_failure("failed", "malformed_output"))
        first = self.item(a)
        self.execute("UPDATE tia_review_items SET due_at = now() - interval '2 hours' WHERE id = %s::uuid;", (first["id"],))
        before = self.item(a)
        for _ in range(3):
            self.accept(self.attempt(a), base.v2_failure("timed_out", "timeout"))
        after = self.item(a)
        self.assertEqual(after["first_seen_at"], first["first_seen_at"])
        self.assertEqual(after["due_at"], before["due_at"], "an overdue item stays overdue; a retry never extends it")
        self.assertEqual(after["occurrences"], 4)
        self.assertEqual(self.events(after["id"]).count("recurred"), 3)

    def test_a_tighter_deadline_moves_earlier_only(self) -> None:
        a = self.alert("medium")
        self.accept(self.attempt(a), base.v2_failure("failed", "malformed_output"))
        before = self.item(a)["due_at"]
        self.accept(self.attempt(a), self.critical_success())  # page: deadline is capped at 60 minutes
        after = self.item(a)["due_at"]
        self.assertLessEqual(after, before)

    def test_acknowledged_item_returns_to_open_only_for_something_worse(self) -> None:
        from app.services import tia_review

        a = self.alert("medium")
        self.accept(self.attempt(a), base.v2_failure("failed", "malformed_output"))
        item = self.item(a)
        tia_review.acknowledge(item["id"], ANALYST)
        self.accept(self.attempt(a), base.v2_failure("failed", "malformed_output"))
        self.assertEqual(self.item(a)["status"], "acknowledged")
        self.accept(self.attempt(a), self.critical_success())
        self.assertEqual(self.item(a)["status"], "open")

    def test_resolved_item_recurrence_is_suppressed_unless_material(self) -> None:
        from app.services import tia_review

        a = self.alert("medium")
        self.accept(self.attempt(a), base.v2_failure("failed", "malformed_output"))
        item = self.item(a)
        tia_review.resolve(item["id"], OFFICER, "checked by a person")
        res = self.accept(self.attempt(a), base.v2_failure("failed", "malformed_output"))
        self.assertEqual(res.review_action, "recurrence_suppressed")
        self.assertEqual(self.item(a)["status"], "resolved")
        res = self.accept(self.attempt(a), self.critical_success())
        self.assertEqual(res.review_action, "reopened")
        reopened = self.item(a)
        self.assertEqual((reopened["status"], reopened["reopened_count"]), ("open", 1))
        self.assertEqual(reopened["first_seen_at"], item["first_seen_at"])
        self.assertEqual(self.events(item["id"]), ["created", "resolved", "recurrence_suppressed", "reopened"])

    def test_success_flags_analysis_available_but_never_resolves(self) -> None:
        a = self.alert("high")
        self.accept(self.attempt(a), base.v2_failure("failed", "malformed_output"))
        self.accept(self.attempt(a), base.v2_success(verdict="Benign", confidence=95))
        item = self.item(a)
        self.assertEqual((item["status"], item["analysis_available"]), ("open", True))
        self.assertIn("analysis_available", self.events(item["id"]))

    def test_provider_outage_notice_is_sent_once_per_category_and_window(self) -> None:
        import time

        for _ in range(3):
            a = self.alert("medium")
            self.accept(self.attempt(a), base.v2_failure("failed", "auth_failure"))
        bucket = int(time.time() // acc.outage_window_seconds())
        keys = {
            "auth_failure": acc._sha(f"outage|auth_failure|{bucket}"),
            "agent_unreachable": acc._sha(f"outage|agent_unreachable|{bucket}"),
        }
        self.assertEqual(self.one("SELECT count(*)::int AS n FROM tia_notifications WHERE base_key = %s;", (keys["auth_failure"],))["n"], 1)
        a = self.alert("medium")
        self.accept(self.attempt(a), base.v2_failure("failed", "agent_unreachable"))
        self.assertEqual(self.one("SELECT count(*)::int AS n FROM tia_notifications WHERE base_key = %s;", (keys["agent_unreachable"],))["n"], 1)
        a = self.alert("medium")
        self.accept(self.attempt(a), base.v2_failure("failed", "malformed_output"))
        self.assertEqual(self.pages(a, "outage_notice"), [])


class ManualReviewModeTests(AcceptanceBase):
    def test_manual_review_mode_creates_a_review_item_and_calls_no_model(self) -> None:
        from app.services import ai_deep_triage as deep

        a = self.alert("critical")
        alert = {"id": a, "tenant_id": self.TENANT_A, "severity": "critical", "ai_triage_status": ""}
        env = {"SOC_AGENT_ENABLED": "true", "TIA_INVESTIGATION_MODE": "manual_review", "SOC_AGENT_MIN_SEVERITY": "medium"}
        with patch.dict(os.environ, env), patch.object(deep, "load_alert_for_triage", return_value=alert), patch(
            "app.services.soc_agent_client.call_agent_ingest"
        ) as call, patch.object(deep, "run_tier1_triage") as ollama:
            self.assertTrue(deep.process_deep_triage_job(alert_id=a, tenant_id=self.TENANT_A))
        call.assert_not_called()
        ollama.assert_not_called()
        item = self.item(a)
        self.assertEqual(item["error_category"], "manual_review_mode")
        self.assertEqual(item["notify_urgency"], "page")
        self.assertIsNone(self.one("SELECT ai_verdict FROM security_alerts WHERE id = %s::uuid;", (a,))["ai_verdict"])
        self.assertEqual(tia_schema.readiness()["investigation_mode"], "normal")
        with patch.dict(os.environ, {"TIA_INVESTIGATION_MODE": "manual_review"}):
            codes = [f["code"] for f in tia_schema.readiness()["faults"]]
        self.assertIn("manual_review_mode_active", codes)


class MissingMigrationTests(AcceptanceBase):
    """Simulates an absent migration by requiring an object that does not exist."""

    def missing(self):
        patcher = patch.object(tia_schema, "REQUIRED_OBJECTS", tia_schema.REQUIRED_OBJECTS + (("tia_table_that_is_absent", ("x",)),))
        patcher.start()
        self.addCleanup(patcher.stop)
        tia_schema.reset_cache()

    def test_acceptance_and_attempts_refuse_and_change_nothing(self) -> None:
        a = self.alert("critical")
        att = self.attempt(a)
        self.missing()
        with self.assertRaises(tia_schema.SchemaNotReady):
            self.accept(att, base.v2_failure("failed", "auth_failure"))
        with self.assertRaises(tia_schema.SchemaNotReady):
            acc.record_attempt_failure(attempt_id=att["attempt_id"], category="timeout", timed_out=True)
        with self.assertRaises(tia_schema.SchemaNotReady):
            self.attempt(a)
        self.assertEqual(self.results(a), [])
        self.assertIsNone(self.item(a))
        self.assertEqual(self.pages(a), [])

    def test_the_job_stops_before_calling_the_agent(self) -> None:
        from app.services import ai_deep_triage as deep

        self.missing()
        alert = {"id": "a", "tenant_id": self.TENANT_A, "severity": "critical", "ai_triage_status": ""}
        with patch.dict(os.environ, {"SOC_AGENT_ENABLED": "true", "SOC_AGENT_MIN_SEVERITY": "medium"}), patch.object(
            deep, "load_alert_for_triage", return_value=alert
        ), patch("app.services.soc_agent_client.call_agent_ingest") as call:
            with self.assertRaises(tia_schema.SchemaNotReady):
                deep.process_deep_triage_job(alert_id="a", tenant_id=self.TENANT_A)
        call.assert_not_called()

    def test_the_callback_is_not_acknowledged(self) -> None:
        from fastapi import HTTPException

        from app.api.routes import soc_agent_callback as route

        a = self.alert("critical")
        att = self.attempt(a)
        self.missing()
        body = route.TriageResultIn(alert_id=a, attempt_id=att["attempt_id"], tenant_id=self.TENANT_A, **{k: base.v2_success()[k] for k in ("ok", "contract", "execution", "llm")})
        with patch.dict(os.environ, {"SOC_AGENT_CALLBACK_TOKEN": "t"}):
            with self.assertRaises(HTTPException) as ctx:
                route.soc_agent_triage_result(body, x_soc_agent_token="t")
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(self.results(a), [])

    def test_queue_keeps_the_job_and_marks_it_recoverable(self) -> None:
        from app.services import ai_alert_queue as q

        self.missing()
        with patch.object(q, "ai_alert_enabled", return_value=True), patch.object(q, "ai_soc_triage_enabled", return_value=False), patch.object(
            q, "deep_triage_enabled", return_value=True
        ), patch.object(q, "process_alert_job", return_value=True), patch.object(
            q, "process_deep_triage_job", side_effect=tia_schema.SchemaNotReady(["x"])
        ):
            self.assertFalse(q._run_ai_pipeline("a", "t"))
        self.assertEqual(q._ctx.reason, "schema_not_ready")
        self.assertIn("schema_not_ready", q.RECOVERABLE_DEAD_REASONS)

    def test_readiness_reports_the_fault_and_the_worker_does_nothing(self) -> None:
        self.missing()
        readiness = tia_schema.readiness()
        self.assertFalse(readiness["ready"])
        self.assertIn("schema_not_ready", [f["code"] for f in readiness["faults"]])
        self.assertEqual(tia_outbox.tick()["skipped"], "schema_not_ready")

    def test_review_routes_answer_503_not_empty_success(self) -> None:
        from fastapi import HTTPException

        from app.api.routes import soc_console as route

        self.missing()
        with self.assertRaises(HTTPException) as ctx:
            route.soc_console_review_queue(
                status_filter=None, tenant_id=None, assigned_to=None, include_resolved=False, limit=10, offset=0, current_user=ANALYST
            )
        self.assertEqual(ctx.exception.status_code, 503)


class DeadLetterTests(unittest.TestCase):
    class FakeRedis:
        def __init__(self) -> None:
            self.lists = {}

        def rpush(self, key, value):
            self.lists.setdefault(key, []).append(value)

        def lrange(self, key, start, end):
            return list(self.lists.get(key, []))[start : (None if end < 0 else end + 1)]

        def lrem(self, key, count, value):
            items = self.lists.get(key, [])
            if value in items:
                items.remove(value)
                return 1
            return 0

        def llen(self, key):
            return len(self.lists.get(key, []))

    def test_only_recoverable_dead_letters_are_requeued_and_bounded(self) -> None:
        from app.services import ai_alert_queue as q

        fake = self.FakeRedis()
        entries = [
            {"alert_id": "a", "tenant_id": "t", "attempts": 4, "dead_reason": "schema_not_ready"},
            {"alert_id": "b", "tenant_id": "t", "attempts": 4, "dead_reason": "job_failed"},
            {"alert_id": "c", "tenant_id": "t", "attempts": 4, "dead_reason": "database_error", "requeues": q.MAX_DEAD_REQUEUES},
        ]
        for e in entries:
            fake.rpush(q.DEAD_KEY, json.dumps(e))
        with patch.object(q, "_redis", return_value=fake), patch.object(q, "_ensure_worker"):
            self.assertEqual(q.requeue_dead_letters(), 1)
            self.assertEqual(q.requeue_dead_letters(), 0)
        moved = json.loads(fake.lists[q.QUEUE_KEY][0])
        self.assertEqual((moved["alert_id"], moved["attempts"], moved["requeues"]), ("a", 0, 1))
        self.assertNotIn("dead_reason", moved)
        self.assertEqual(fake.llen(q.DEAD_KEY), 2)


class NotificationOutboxTests(AcceptanceBase):
    def critical_failure_page(self, severity="critical"):
        a = self.alert(severity)
        self.accept(self.attempt(a), base.v2_failure("failed", "auth_failure"))
        return a

    def test_crash_after_commit_before_delivery_recovers(self) -> None:
        a = self.critical_failure_page()
        rows = self.pages(a)
        self.assertEqual([r["state"] for r in rows], ["required"])  # committed, nothing sent yet: the "crash"
        self.assertEqual(self.transport.sent, [])
        tia_outbox.deliver_pending(500)  # a new worker after restart
        self.assertEqual(self.pages(a)[0]["state"], "submitted")
        self.assertEqual(sum(1 for s in self.transport.sent if s[1] == ROSTER), len(self.transport.sent))

    def test_a_crash_during_send_is_reclaimed_after_the_lease_and_not_before(self) -> None:
        a = self.critical_failure_page()
        self.execute(
            "UPDATE tia_notifications SET state = 'queued', attempts = 1, locked_until = now() + interval '5 minutes' WHERE alert_id = %s::uuid;",
            (a,),
        )
        tia_outbox.deliver_pending(500)
        self.assertEqual(self.pages(a)[0]["state"], "queued", "a live lease is respected")
        self.execute("UPDATE tia_notifications SET locked_until = now() - interval '1 second' WHERE alert_id = %s::uuid;", (a,))
        tia_outbox.deliver_pending(500)
        self.assertEqual(self.pages(a)[0]["state"], "submitted")

    def test_submitted_is_not_delivered_until_a_provider_receipt(self) -> None:
        a = self.critical_failure_page()
        tia_outbox.deliver_pending(500)
        row = self.pages(a)[0]
        self.assertEqual((row["state"], row["delivery_evidence"]), ("submitted", "provider_accepted"))
        self.assertIsNone(row["delivered_at"])
        self.assertEqual(self.item(a)["notification_state"], "page_submitted")
        self.assertFalse(tia_outbox.record_delivery_receipt("wamid.unknown"))
        message_id = row["provider_message_id"]
        self.assertTrue(tia_outbox.record_delivery_receipt(message_id))
        row = self.pages(a)[0]
        self.assertEqual((row["state"], row["delivery_evidence"]), ("delivered", "provider_delivery_receipt"))
        self.assertEqual(self.item(a)["notification_state"], "page_delivered")
        self.assertFalse(tia_outbox.record_delivery_receipt(message_id), "only a submitted row can become delivered")

    def test_transient_failure_retries_with_backoff_then_succeeds(self) -> None:
        a = self.critical_failure_page()
        self.transport.fail_times = 1
        tia_outbox.deliver_pending(500)
        row = self.pages(a)[0]
        self.assertEqual((row["state"], row["attempts"]), ("required", 1))
        self.assertIn("synthetic transport failure", row["last_error"])
        self.assertEqual(self.one("SELECT next_attempt_at > now() AS later FROM tia_notifications WHERE id = %s::uuid;", (row["id"],))["later"], True)
        tia_outbox.deliver_pending(500)
        self.assertEqual(self.pages(a)[0]["state"], "required", "not retried before the backoff elapses")
        self.make_due(a)
        tia_outbox.deliver_pending(500)
        row = self.pages(a)[0]
        self.assertEqual((row["state"], row["attempts"]), ("submitted", 2))

    def test_retries_are_bounded_and_the_failure_is_visible(self) -> None:
        a = self.critical_failure_page()
        self.transport.fail_times = 99
        with patch.dict(os.environ, {"TIA_NOTIFY_MAX_ATTEMPTS": "2"}):
            self.execute("UPDATE tia_notifications SET max_attempts = 2 WHERE alert_id = %s::uuid;", (a,))
            for _ in range(4):
                tia_outbox.deliver_pending(500)
                self.make_due(a)
        row = self.pages(a)[0]
        self.assertEqual((row["state"], row["attempts"]), ("failed", 2))
        self.assertIsNotNone(row["failed_at"])
        self.assertEqual(self.item(a)["notification_state"], "page_failed")
        readiness = tia_schema.readiness()
        self.assertIn("notification_delivery_failed", [f["code"] for f in readiness["faults"]])
        self.assertFalse(readiness["ready"])

    def test_permanent_failure_is_not_retried(self) -> None:
        a = self.critical_failure_page()
        self.transport.fail_times, self.transport.permanent = 99, True
        tia_outbox.deliver_pending(500)
        row = self.pages(a)[0]
        self.assertEqual((row["state"], row["attempts"]), ("failed", 1))

    def test_missing_oncall_configuration_is_a_visible_fault_not_a_working_pager(self) -> None:
        with patch.dict(os.environ, {"SOC_ONCALL_WHATSAPP": ""}):
            codes = [f["code"] for f in tia_schema.notification_config_faults()]
            self.assertIn("oncall_roster_not_configured", codes)
            readiness = tia_schema.readiness()
            self.assertFalse(readiness["ready"])
            a = self.critical_failure_page()
            row = self.pages(a)[0]
            self.assertEqual((row["state"], row["recipient_address"], row["blocked_reason"]), ("required", None, "no_recipients_configured"))
            self.assertEqual(self.item(a)["notification_state"], "no_recipients_configured")
            tia_outbox.deliver_pending(500)
            self.assertEqual(self.pages(a)[0]["state"], "required", "nothing is claimed as sent")
            self.assertGreaterEqual(tia_schema.readiness()["backlog"]["blocked_notifications"], 1)
            from app.services import tia_review

            self.assertGreaterEqual(tia_review.summary()["undeliverable_page_count"], 1)
        # configuring a roster later releases the page that was waiting
        self.assertGreaterEqual(tia_outbox.expand_blocked(), 1)
        row = self.pages(a)[0]
        self.assertEqual(row["recipient_address"], ROSTER)
        tia_outbox.deliver_pending(500)
        self.assertEqual(self.pages(a)[0]["state"], "submitted")

    def test_acknowledgement_overdue_escalates_once_to_the_configured_target(self) -> None:
        with patch.dict(os.environ, {"SOC_ONCALL_ESCALATION_WHATSAPP": ESCALATION}):
            a = self.critical_failure_page()
            tia_outbox.deliver_pending(500)
            self.execute("UPDATE tia_notifications SET ack_due_at = now() - interval '1 minute' WHERE alert_id = %s::uuid;", (a,))
            self.assertGreaterEqual(tia_outbox.escalate_overdue(), 1)
            level2 = self.all("SELECT * FROM tia_notifications WHERE alert_id = %s::uuid AND level = 2;", (a,))
            self.assertEqual([(r["recipient_address"], r["state"]) for r in level2], [(ESCALATION, "required")])
            self.assertTrue(level2[0]["message_body"].startswith("[ESCALATION"))
            tia_outbox.escalate_overdue()
            self.assertEqual(len(self.all("SELECT 1 FROM tia_notifications WHERE alert_id = %s::uuid AND level = 2;", (a,))), 1)
            self.assertIn("ack_overdue_escalated", self.events(self.item(a)["id"]))
            tia_outbox.deliver_pending(500)
            self.assertEqual(self.all("SELECT state FROM tia_notifications WHERE alert_id = %s::uuid AND level = 2;", (a,))[0]["state"], "submitted")

    def test_overdue_acknowledgement_without_an_escalation_target_is_visible(self) -> None:
        a = self.critical_failure_page()
        tia_outbox.deliver_pending(500)
        self.execute("UPDATE tia_notifications SET ack_due_at = now() - interval '1 minute' WHERE alert_id = %s::uuid;", (a,))
        tia_outbox.escalate_overdue()
        level2 = self.all("SELECT * FROM tia_notifications WHERE alert_id = %s::uuid AND level = 2;", (a,))
        self.assertEqual([(r["recipient_address"], r["blocked_reason"]) for r in level2], [(None, "escalation_target_not_configured")])
        codes = [f["code"] for f in tia_schema.readiness()["faults"]]
        self.assertIn("escalation_target_not_configured", codes)
        self.assertIn("acknowledgement_overdue", codes)

    def test_an_acknowledged_page_is_not_escalated(self) -> None:
        from app.services import tia_review

        with patch.dict(os.environ, {"SOC_ONCALL_ESCALATION_WHATSAPP": ESCALATION}):
            a = self.critical_failure_page()
            tia_outbox.deliver_pending(500)
            tia_review.acknowledge(self.item(a)["id"], ANALYST)
            self.execute("UPDATE tia_notifications SET ack_due_at = now() - interval '1 minute' WHERE alert_id = %s::uuid;", (a,))
            tia_outbox.escalate_overdue()
            self.assertEqual(self.all("SELECT 1 FROM tia_notifications WHERE alert_id = %s::uuid AND level = 2;", (a,)), [])


class ReviewActionTests(AcceptanceBase):
    def make_item(self, severity="critical", sent=True):
        a = self.alert(severity)
        self.accept(self.attempt(a), base.v2_failure("failed", "auth_failure"))
        if sent:
            tia_outbox.deliver_pending(500)
        return a, self.item(a)

    def test_customer_roles_are_refused_for_reads_and_actions(self) -> None:
        from fastapi import HTTPException

        from app.api.dependencies import require_roles
        from app.api.routes.admin import ADMIN_SOC_ROLES
        from app.services import tia_review

        _, item = self.make_item()
        check = require_roles(*ADMIN_SOC_ROLES)
        for role in ("customer_admin", "customer_viewer"):
            with self.assertRaises(HTTPException) as ctx:
                check(current_user={"role": role})
            self.assertEqual(ctx.exception.status_code, 403)
        for action in (tia_review.acknowledge, tia_review.resolve, tia_review.reopen):
            with self.assertRaises(tia_review.ReviewError) as ctx:
                action(item["id"], CUSTOMER, "a long enough note")
            self.assertEqual(ctx.exception.http, 403)
        with self.assertRaises(tia_review.ReviewError):
            tia_review.assign(item["id"], CUSTOMER, "someone@example.test")

    def test_a_customer_database_context_cannot_see_another_tenants_items(self) -> None:
        from app.db import session
        from app.services import tia_review

        _, item = self.make_item()
        tokens = session.set_db_session_context(tenant_id=self.TENANT_B, role="customer_admin")
        try:
            self.assertNotIn(item["id"], [i["id"] for i in tia_review.list_items(limit=300)["items"]])
            self.assertEqual(tia_review.summary(self.TENANT_A)["open_count"], 0)
            with self.assertRaises(tia_review.ReviewError) as ctx:
                tia_review.get_item(item["id"])
            self.assertEqual(ctx.exception.http, 404)
        finally:
            session._current_tenant.reset(tokens[0])
            session._current_role.reset(tokens[1])

    def test_list_detail_and_counts_show_what_an_analyst_needs(self) -> None:
        from app.services import tia_review

        a, item = self.make_item()
        listing = tia_review.list_items(limit=300)
        row = next(i for i in listing["items"] if i["id"] == item["id"])
        for key in ("customer_name", "case_title", "alert_id", "reason_code", "assessed_priority", "assigned_to", "age_seconds", "due_at", "overdue", "status", "error_category", "notification_state", "notification_counts", "deadline_basis"):
            self.assertIn(key, row)
        self.assertEqual((row["deadline_basis"], listing["deadline_basis"]), ("provisional", "provisional"))
        self.assertEqual(row["notification_counts"], {"submitted": 1})
        detail = tia_review.get_item(item["id"])
        self.assertEqual(detail["customer_code"], "TIAACC1")
        self.assertTrue(detail["events"] and detail["attempts"] and detail["results"] and detail["notifications"])
        text = json.dumps(detail, default=str)
        self.assertNotIn(ROSTER, text, "recipient numbers are masked")
        self.assertIn(ROSTER[-4:], text)
        self.assertNotIn("raw_event", text)
        self.assertNotIn(item["id"], [i["id"] for i in tia_review.list_items(status="resolved", limit=300)["items"]])
        summary = tia_review.summary()
        self.assertGreaterEqual(summary["open_count"], 1)
        self.assertEqual(summary["deadline_basis"], "provisional")
        with self.assertRaises(tia_review.ReviewError) as ctx:
            tia_review.get_item(str(uuid.uuid4()))
        self.assertEqual(ctx.exception.http, 404)

    def test_acknowledge_takes_ownership_without_resolving_the_case(self) -> None:
        from app.services import tia_review

        a, item = self.make_item()
        self.execute("UPDATE tia_notifications SET state = 'required', submitted_at = NULL WHERE alert_id = %s::uuid;", (a,))
        res = tia_review.acknowledge(item["id"], ANALYST, "on it")
        self.assertEqual((res["changed"], res["status"], res["cancelled"], res["acknowledged"]), (True, "acknowledged", 1, 0))
        self.assertEqual(self.item(a)["status"], "acknowledged")
        self.assertEqual(self.one("SELECT status FROM security_alerts WHERE id = %s::uuid;", (a,))["status"], "new")
        self.assertFalse(tia_review.acknowledge(item["id"], ANALYST)["changed"])
        self.assertEqual(self.pages(a)[0]["state"], "cancelled")
        audit = self.one("SELECT count(*)::int AS n FROM audit_logs WHERE action = 'tia.review.acknowledge' AND entity_id = %s::uuid;", (item["id"],))
        self.assertEqual(audit["n"], 1)
        event = self.one("SELECT actor, detail FROM tia_review_events WHERE review_item_id = %s::uuid AND event_type = 'acknowledged';", (item["id"],))
        self.assertEqual(event["actor"], ANALYST["email"])
        self.assertTrue(event["detail"]["case_status_unchanged"])

    def test_acknowledging_a_sent_page_records_who_acknowledged(self) -> None:
        from app.services import tia_review

        a, item = self.make_item()
        res = tia_review.acknowledge(item["id"], ANALYST)
        self.assertEqual(res["acknowledged"], 1)
        row = self.pages(a)[0]
        self.assertEqual((row["state"], row["acknowledged_by"]), ("acknowledged", ANALYST["email"]))
        self.assertEqual(self.item(a)["notification_state"], "acknowledged")

    def test_assignment_rules_by_role(self) -> None:
        from app.services import tia_review

        _, item = self.make_item()
        self.assertEqual(tia_review.assign(item["id"], OFFICER, ANALYST["email"])["assigned_to"], ANALYST["email"])
        with self.assertRaises(tia_review.ReviewError) as ctx:
            tia_review.assign(item["id"], ANALYST, ANALYST2["email"])
        self.assertEqual(ctx.exception.http, 403)
        with self.assertRaises(tia_review.ReviewError) as ctx:
            tia_review.assign(item["id"], ANALYST2, None)  # cannot take an item owned by someone else
        self.assertEqual(ctx.exception.http, 403)
        self.assertFalse(tia_review.assign(item["id"], ANALYST, None)["changed"])
        self.assertEqual(tia_review.assign(item["id"], ADMIN, ANALYST2["email"])["assigned_to"], ANALYST2["email"])
        self.assertIn("assigned", self.events(item["id"]))

    def test_resolve_needs_a_note_and_the_right_role(self) -> None:
        from app.services import tia_review

        a, item = self.make_item(sent=False)
        with self.assertRaises(tia_review.ReviewError) as ctx:
            tia_review.resolve(item["id"], OFFICER, "no")
        self.assertEqual(ctx.exception.http, 422)
        with self.assertRaises(tia_review.ReviewError) as ctx:
            tia_review.resolve(item["id"], ANALYST, "not mine to close")
        self.assertEqual(ctx.exception.http, 403)
        tia_review.assign(item["id"], ANALYST, None)
        self.assertEqual(tia_review.resolve(item["id"], ANALYST, "verified with the customer")["status"], "resolved")
        row = self.item(a)
        self.assertEqual((row["status"], row["resolved_by"], row["resolution_note"]), ("resolved", ANALYST["email"], "verified with the customer"))
        self.assertEqual(self.pages(a)[0]["state"], "cancelled", "a page that was never sent is cancelled")
        self.assertEqual(self.one("SELECT status FROM security_alerts WHERE id = %s::uuid;", (a,))["status"], "new")
        self.assertFalse(tia_review.resolve(item["id"], OFFICER, "already done here")["changed"])
        with self.assertRaises(tia_review.ReviewError) as ctx:
            tia_review.acknowledge(item["id"], ANALYST)
        self.assertEqual(ctx.exception.http, 409)

    def test_reopen_is_manager_only_needs_a_note_and_resets_the_deadline_by_policy(self) -> None:
        from app.services import tia_review

        a, item = self.make_item()
        with self.assertRaises(tia_review.ReviewError) as ctx:
            tia_review.reopen(item["id"], OFFICER, "still open")
        self.assertEqual(ctx.exception.http, 409)
        tia_review.resolve(item["id"], OFFICER, "closed in error here")
        for user, expected in ((ANALYST, 403), (OFFICER, 422)):
            with self.assertRaises(tia_review.ReviewError) as ctx:
                tia_review.reopen(item["id"], user, "no" if user is OFFICER else "a reason that is long enough")
            self.assertEqual(ctx.exception.http, expected)
        self.assertEqual(tia_review.reopen(item["id"], OFFICER, "closed in error — reopening")["status"], "open")
        row = self.item(a)
        self.assertEqual((row["status"], row["reopened_count"]), ("open", 1))
        self.assertEqual(self.events(item["id"])[-1], "reopened")
        self.assertEqual(self.one("SELECT status FROM security_alerts WHERE id = %s::uuid;", (a,))["status"], "new")

    def test_routes_map_refusals_to_http_codes(self) -> None:
        from fastapi import HTTPException

        from app.api.routes import soc_console as route

        _, item = self.make_item()
        listing = route.soc_console_review_queue(
            status_filter="open", tenant_id=uuid.UUID(self.TENANT_A), assigned_to=None, include_resolved=False, limit=50, offset=0, current_user=ANALYST
        )
        self.assertIn(item["id"], [i["id"] for i in listing["items"]])
        self.assertTrue(all(i["status"] == "open" and i["tenant_id"] == self.TENANT_A for i in listing["items"]))
        with self.assertRaises(HTTPException) as ctx:
            route.soc_console_review_resolve(uuid.UUID(item["id"]), route.ReviewNoteIn(note="x"), current_user=OFFICER)
        self.assertEqual(ctx.exception.status_code, 422)
        with self.assertRaises(HTTPException) as ctx:
            route.soc_console_review_detail(uuid.uuid4(), current_user=ANALYST)
        self.assertEqual(ctx.exception.status_code, 404)
        done = route.soc_console_review_acknowledge(uuid.UUID(item["id"]), route.ReviewNoteIn(), current_user=ANALYST)
        self.assertEqual(done["status"], "acknowledged")

    def test_the_operator_summary_surfaces_a_readiness_fault(self) -> None:
        with patch.dict(os.environ, {"SOC_ONCALL_WHATSAPP": ""}):
            codes = [f["code"] for f in tia_schema.readiness()["faults"] if f["severity"] == "fault"]
        self.assertIn("oncall_roster_not_configured", codes)


class CallbackRouteTests(AcceptanceBase):
    def call(self, body, token="t"):
        from app.api.routes import soc_agent_callback as route

        with patch.dict(os.environ, {"SOC_AGENT_CALLBACK_TOKEN": "t"}):
            return route.soc_agent_triage_result(body, x_soc_agent_token=token)

    def body(self, a, att, **over):
        from app.api.routes.soc_agent_callback import TriageResultIn

        raw = over.pop("raw", base.v2_success(verdict="Suspicious", confidence=70))
        fields = {k: raw[k] for k in ("ok", "contract", "execution", "llm") if k in raw}
        kwargs = {"alert_id": a, "attempt_id": att["attempt_id"], "tenant_id": self.TENANT_A, "job_id": att["job_id"], "evidence_version": att["evidence_version"], **fields}
        kwargs.update(over)
        return TriageResultIn(**kwargs)

    def test_status_codes(self) -> None:
        from fastapi import HTTPException

        a = self.alert("high")
        att = self.attempt(a)
        ok = self.call(self.body(a, att))
        self.assertEqual((ok["ok"], ok["status"], ok["applied"]), (True, "accepted", True))
        self.assertEqual(self.call(self.body(a, att))["status"], "duplicate")
        for label, body, code in (
            ("bad token", None, 401),
            ("wrong tenant", self.body(a, att, tenant_id=self.TENANT_B), 409),
            ("conflicting payload", self.body(a, att, raw=self.critical_success()), 409),
            ("unknown attempt", self.body(a, {**att, "attempt_id": str(uuid.uuid4())}), 404),
        ):
            with self.subTest(label):
                with self.assertRaises(HTTPException) as ctx:
                    self.call(body or self.body(a, att), token="bad" if body is None else "t")
                self.assertEqual(ctx.exception.status_code, code)

    def test_required_test_dependencies_are_installed(self) -> None:
        self.assertEqual(tia_testenv.missing_test_modules(), [], "install backend-api/requirements-test.txt")

    def test_the_real_app_serves_the_callback_and_protects_the_review_queue(self) -> None:
        from fastapi.testclient import TestClient

        from app.main import app

        a = self.alert("high")
        att = self.attempt(a)
        raw = base.v2_success(verdict="Suspicious", confidence=70)
        payload = {
            "alert_id": a, "attempt_id": att["attempt_id"], "tenant_id": self.TENANT_A, "job_id": att["job_id"],
            "evidence_version": att["evidence_version"], **{k: raw[k] for k in ("ok", "contract", "execution", "llm")},
        }
        client = TestClient(app)
        with patch.dict(os.environ, {"SOC_AGENT_CALLBACK_TOKEN": "t"}):
            self.assertEqual(client.post("/api/v1/soc-agent/triage-result", json=payload, headers={"X-Soc-Agent-Token": "bad"}).status_code, 401)
            first = client.post("/api/v1/soc-agent/triage-result", json=payload, headers={"X-Soc-Agent-Token": "t"})
            self.assertEqual((first.status_code, first.json()["status"]), (200, "accepted"))
            again = client.post("/api/v1/soc-agent/triage-result", json=payload, headers={"X-Soc-Agent-Token": "t"})
            self.assertEqual(again.json()["status"], "duplicate")
            wrong = client.post("/api/v1/soc-agent/triage-result", json={**payload, "tenant_id": self.TENANT_B}, headers={"X-Soc-Agent-Token": "t"})
            self.assertEqual(wrong.status_code, 409)
            missing = {k: v for k, v in payload.items() if k != "attempt_id"}
            self.assertEqual(client.post("/api/v1/soc-agent/triage-result", json=missing, headers={"X-Soc-Agent-Token": "t"}).status_code, 422)
        for method, path in (
            ("get", "/admin/soc-console/review-queue"),
            ("get", f"/admin/soc-console/review-queue/{uuid.uuid4()}"),
            ("get", "/admin/soc-console/tia-readiness"),
            ("post", f"/admin/soc-console/review-queue/{uuid.uuid4()}/acknowledge"),
            ("post", f"/admin/soc-console/review-queue/{uuid.uuid4()}/resolve"),
        ):
            kwargs = {"json": {}} if method == "post" else {}
            self.assertEqual(getattr(client, method)(path, **kwargs).status_code, 401, path)

    def test_a_database_failure_is_not_acknowledged(self) -> None:
        from fastapi import HTTPException

        a = self.alert("critical")
        att = self.attempt(a)
        with patch.object(acc, "_enqueue_page", side_effect=RuntimeError("db down")):
            with self.assertRaises(HTTPException) as ctx:
                self.call(self.body(a, att, raw=base.v2_failure("failed", "auth_failure")))
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(self.results(a), [])


class LiveNotificationIntegration(unittest.TestCase):
    """Prepared real-transport test. Skipped unless explicitly enabled.

    Sends ONE message to a destination the operator designates for the test, never
    to the on-call roster. Required environment:
        TIA_LIVE_TEST_DESTINATION   the designated test number
        TIA_LIVE_TEST_CONFIRM       must equal that number (explicit confirmation)
        WHATSAPP_ACCESS_TOKEN / WHATSAPP_PHONE_NUMBER_ID (provider credentials)
    It is never run by the local suite.
    """

    @unittest.skipUnless(
        os.getenv("TIA_LIVE_TEST_DESTINATION") and os.getenv("TIA_LIVE_TEST_CONFIRM") == os.getenv("TIA_LIVE_TEST_DESTINATION"),
        "live notification test not enabled",
    )
    def test_one_message_to_the_designated_destination(self) -> None:
        destination = os.environ["TIA_LIVE_TEST_DESTINATION"]
        roster = tia_schema.split_roster(os.getenv("SOC_ONCALL_WHATSAPP")) + tia_schema.split_roster(os.getenv("SOC_ONCALL_ESCALATION_WHATSAPP"))
        self.assertNotIn(destination, roster, "refusing to message an on-call or escalation contact")
        receipt = tia_outbox._default_transport("whatsapp", destination, "[TIA integration test] synthetic message, no action needed.")
        self.assertTrue(receipt.message_id, "provider accepted the message (this is acceptance, not delivery)")


if __name__ == "__main__":
    unittest.main()
