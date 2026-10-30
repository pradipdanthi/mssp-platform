"""Acceptance gate, increment 1: a failed investigation never becomes a benign verdict.

Pure tests run anywhere. DB-backed tests need a Postgres initialised from
postgres/init (including 117 and 118) and skip otherwise.

The audited fixture is the legacy agent reply produced when the Cursor call
failed: ok=true, verdict "Benign", provider "heuristic_fallback_cursor_error".
"""

from __future__ import annotations

import os
import unittest
import uuid
from unittest.mock import patch

from app.services import ai_deep_triage as deep
from app.services import soc_agent_expert as expert
from app.services import tia_investigation as tia
from app.services.soc_agent_client import AgentCallError


def audited_fixture() -> dict:
    """The exact shape the old agent returned on a Cursor failure (legacy contract)."""
    return {
        "ok": True,
        "alert_id": "00000000-0000-0000-0000-0000000000a1",
        "verdict": "Benign",
        "llm": {
            "verdict": "Benign",
            "confidence": 10,
            "summary": "Cursor LLM call failed — heuristic only. no strong signals",
            "root_cause": "cursor_llm_error",
            "mitre": [],
            "recommended_actions": ["Check CURSOR_API_KEY and agent CLI on VM 117"],
            "false_positive_likelihood": "medium",
            "escalate_to_human": True,
        },
        "llm_meta": {"provider": "heuristic_fallback_cursor_error", "error": "boom"},
        "human_soc_effort": "auto_closed_or_low_touch",
    }


def v2_failure(status: str, category: str) -> dict:
    return {
        "ok": False,
        "contract": "analyst-result-2",
        "execution": {"status": status, "error_category": category, "provider": "cursor-agent"},
        "disposition": "unset",
        "verdict": None,
        "llm": None,
    }


def v2_success(**llm_over) -> dict:
    llm = {
        "verdict": "Suspicious",
        "confidence": 70,
        "summary": "Synthetic analysis.",
        "escalate_to_human": False,
    }
    llm.update(llm_over)
    return {
        "ok": True,
        "contract": "analyst-result-2",
        "execution": {
            "status": "succeeded",
            "provider": "cursor-agent",
            "model_selector": "account_default",
            "cli_version": "9.9.9",
            "prompt_version": "soc-analyst-1",
        },
        "llm": llm,
    }


class NormalizationTests(unittest.TestCase):
    def test_audited_fixture_is_a_failure_not_a_benign_verdict(self) -> None:
        for sev in ("critical", "high", "medium"):
            out = tia.normalize_agent_result(audited_fixture(), source="agent_http", source_severity=sev)
            self.assertFalse(out.succeeded)
            self.assertEqual(out.error_category, "legacy_heuristic_fallback")
            self.assertIsNone(out.verdict_db)
            self.assertIsNone(out.llm)
            self.assertEqual(out.disposition, "unset")
            self.assertTrue(out.model_review_requested)
            self.assertEqual(out.source_severity, sev)

    def test_agent_reported_failures_keep_their_status(self) -> None:
        out = tia.normalize_agent_result(v2_failure("timed_out", "timeout"), source="agent_http", source_severity="high")
        self.assertEqual((out.execution_status, out.error_category), ("timed_out", "timeout"))
        out = tia.normalize_agent_result(v2_failure("failed", "auth_failure"), source="agent_http", source_severity="high")
        self.assertEqual((out.execution_status, out.error_category), ("failed", "auth_failure"))

    def test_unknown_category_becomes_unexpected_error(self) -> None:
        out = tia.normalize_agent_result(v2_failure("failed", "made up"), source="agent_http")
        self.assertEqual(out.error_category, "unexpected_error")

    def test_ok_true_without_valid_analysis_is_a_failure(self) -> None:
        cases = {
            "no llm": {**v2_success(), "llm": None},
            "empty llm": {**v2_success(), "llm": {}},
            "missing summary": v2_success(summary=""),
            "missing verdict": v2_success(verdict=None),
            "unknown verdict": v2_success(verdict="All clear"),
            "string confidence": v2_success(confidence="high"),
            "bool confidence": v2_success(confidence=True),
            "confidence out of range": v2_success(confidence=250),
            "not a dict": {**v2_success(), "llm": "Benign"},
        }
        for name, raw in cases.items():
            with self.subTest(name):
                out = tia.normalize_agent_result(raw, source="agent_http", source_severity="high")
                self.assertFalse(out.succeeded)
                self.assertIsNone(out.verdict_db)
                self.assertEqual(out.disposition, "unset")

    def test_succeeded_status_with_ok_false_is_a_failure(self) -> None:
        raw = v2_success()
        raw["ok"] = False
        self.assertFalse(tia.normalize_agent_result(raw, source="agent_http").succeeded)

    def test_non_dict_and_none(self) -> None:
        for raw in (None, [], "x", 5):
            out = tia.normalize_agent_result(raw, source="agent_http")
            self.assertFalse(out.succeeded)
            self.assertEqual(out.error_category, "agent_bad_response")

    def test_success_is_validated_with_honest_provenance(self) -> None:
        out = tia.normalize_agent_result(v2_success(), source="agent_http", source_severity="high")
        self.assertTrue(out.succeeded)
        self.assertEqual(out.verdict_db, "SUSPICIOUS")
        self.assertEqual(out.disposition, "inconclusive")
        prov = out.provenance
        self.assertEqual(prov["resolved_model"], "unknown")
        self.assertIsNone(prov["model_selector"], "account_default must not be presented as a model")
        self.assertEqual(prov["cli_version"], "9.9.9")
        self.assertEqual(prov["prompt_version"], "soc-analyst-1")

    def test_model_benign_is_inconclusive_never_false_positive(self) -> None:
        out = tia.normalize_agent_result(v2_success(verdict="Benign", confidence=99), source="agent_http", source_severity="high")
        self.assertTrue(out.succeeded)
        self.assertEqual(out.verdict_db, "BENIGN_FALSE_POSITIVE")
        self.assertEqual(out.disposition, "inconclusive")

    def test_model_cannot_choose_notification_destination_or_suppress(self) -> None:
        raw = v2_success(
            verdict="Benign",
            confidence=99,
            notification_destination="+15550000000",
            notify=["+15550000001"],
            suppress_escalation=True,
            review_required=False,
        )
        out = tia.normalize_agent_result(raw, source="agent_http", source_severity="critical")
        blob = repr(out.llm)
        for forbidden in ("notification_destination", "+1555", "suppress_escalation", "review_required", "notify"):
            self.assertNotIn(forbidden, blob)

    def test_transport_failures(self) -> None:
        self.assertEqual(tia.transport_failure("agent_unreachable").execution_status, "failed")
        out = tia.transport_failure("timeout", timed_out=True)
        self.assertEqual((out.execution_status, out.error_category), ("timed_out", "timeout"))
        self.assertFalse(out.succeeded)


class ReviewDecisionTests(unittest.TestCase):
    def decide(self, severity: str, status: str, **kw):
        return tia.decide_review(
            source_severity=severity,
            asset_criticality=kw.pop("asset", ""),
            execution_status=status,
            **kw,
        )

    def test_every_failure_status_requires_review_on_every_severity(self) -> None:
        for status in ("failed", "timed_out", "degraded"):
            for sev in ("critical", "high", "medium", "low"):
                d = self.decide(sev, status, error_category="timeout")
                self.assertTrue(d["review_required"], (status, sev))
                self.assertIsNotNone(d["due_minutes"])
                self.assertEqual(d["source_severity"], sev)

    def test_critical_failure_pages_and_non_urgent_does_not(self) -> None:
        self.assertTrue(self.decide("critical", "failed", error_category="auth_failure")["escalate"])
        self.assertTrue(self.decide("high", "failed", asset="critical")["escalate"])
        for sev in ("high", "medium", "low"):
            d = self.decide(sev, "failed", error_category="auth_failure")
            self.assertFalse(d["escalate"], sev)
            self.assertTrue(d["review_required"])

    def test_review_and_page_are_independent_and_priority_is_assessed(self) -> None:
        high = self.decide("high", "timed_out", error_category="timeout")
        self.assertTrue(high["review_required"] and not high["escalate"])
        self.assertEqual(high["assessed_priority"], "P2")
        self.assertEqual(high["source_severity"], "high")
        crit = self.decide("critical", "failed")
        self.assertEqual(crit["assessed_priority"], "P1")
        self.assertLess(crit["due_minutes"], high["due_minutes"])

    def test_degraded_benign_is_discarded_never_silences(self) -> None:
        for sev in ("critical", "high", "medium"):
            d = self.decide(sev, "degraded", verdict="BENIGN_FALSE_POSITIVE", confidence=95)
            self.assertTrue(d["review_required"], sev)
            self.assertNotIn("benign", " ".join(d["reasons"]).lower().replace("benign reading", ""))

    def test_degraded_can_still_raise_concern(self) -> None:
        d = self.decide("high", "degraded", verdict="MALICIOUS", confidence=80)
        self.assertTrue(d["escalate"])

    def test_model_can_request_review_but_not_remove_it(self) -> None:
        asked = self.decide("medium", "succeeded", verdict="BENIGN_FALSE_POSITIVE", confidence=99, model_review_requested=True)
        self.assertTrue(asked["review_required"])
        self.assertFalse(asked["escalate"])
        # A model asking for *no* review has no input: a critical, unsure benign still pages.
        d = self.decide("critical", "succeeded", verdict="BENIGN_FALSE_POSITIVE", confidence=40)
        self.assertTrue(d["escalate"] and d["review_required"])

    def test_confident_benign_stays_a_recommendation(self) -> None:
        d = self.decide("high", "succeeded", verdict="BENIGN_FALSE_POSITIVE", confidence=95)
        self.assertFalse(d["escalate"])
        self.assertFalse(d["review_required"])

    def test_deadlines_come_from_environment_when_set(self) -> None:
        with patch.dict(os.environ, {"TIA_REVIEW_DUE_MINUTES_HIGH": "45"}):
            self.assertEqual(self.decide("high", "failed")["due_minutes"], 45)

    def test_decide_escalation_reads_status_not_model_name(self) -> None:
        alert = {"severity": "critical", "asset_criticality": ""}
        by_name = {"verdict": "SUSPICIOUS", "confidence": 55, "model": "x-fallback-y", "execution_status": "succeeded"}
        self.assertFalse(deep.decide_escalation(alert, by_name)["degraded"])
        missing = {"verdict": "SUSPICIOUS", "confidence": 55, "model": "qwen"}
        self.assertTrue(deep.decide_escalation(alert, missing)["degraded"])


class ExpertPathFailureTests(unittest.TestCase):
    """Every failure normalises to a verdict-less triage: never None, never benign.

    (Increment 2: the agent call and persistence moved into tia_acceptance, so this
    class checks the normalisation the acceptance function relies on. The same
    inputs go through the real acceptance transaction in test_tia_acceptance.py.)
    """

    def triage_for(self, *, raises=None, returns=None, severity="high"):
        if raises is not None:
            outcome = tia.transport_failure(
                raises.category, timed_out=raises.timed_out, error=raises.detail or None, source_severity=severity
            )
        else:
            outcome = tia.normalize_agent_result(returns, source="agent_http", source_severity=severity)
        return expert.outcome_to_triage(outcome)

    def assert_failed(self, triage, status=None, category=None):
        self.assertIsNotNone(triage)
        self.assertNotEqual(triage["execution_status"], "succeeded")
        self.assertIsNone(triage["verdict"])
        self.assertIsNone(triage["confidence"])
        self.assertEqual(triage["disposition"], "unset")
        if status:
            self.assertEqual(triage["execution_status"], status)
        if category:
            self.assertEqual(triage["error_category"], category)

    def test_transport_errors(self) -> None:
        for sev in ("critical", "high", "medium"):
            self.assert_failed(self.triage_for(raises=AgentCallError("agent_unreachable"), severity=sev), "failed", "agent_unreachable")
            self.assert_failed(self.triage_for(raises=AgentCallError("timeout", timed_out=True), severity=sev), "timed_out", "timeout")
            self.assert_failed(self.triage_for(raises=AgentCallError("auth_failure"), severity=sev), "failed", "auth_failure")

    def test_audited_fixture_through_the_http_path(self) -> None:
        for sev in ("critical", "high", "medium"):
            self.assert_failed(self.triage_for(returns=audited_fixture(), severity=sev), "failed", "legacy_heuristic_fallback")

    def test_malformed_empty_and_missing_field_replies(self) -> None:
        for name, raw in {
            "empty object": {},
            "ok no llm": {"ok": True},
            "v2 success without analysis": {**v2_success(), "llm": None},
            "v2 missing summary": v2_success(summary=None),
            "v2 failed": v2_failure("failed", "malformed_output"),
        }.items():
            with self.subTest(name):
                self.assert_failed(self.triage_for(returns=raw))

    def test_valid_success_maps_to_a_validated_triage(self) -> None:
        triage = self.triage_for(returns=v2_success())
        self.assertEqual(triage["execution_status"], "succeeded")
        self.assertEqual(triage["verdict"], "SUSPICIOUS")
        self.assertEqual(triage["provenance"]["resolved_model"], "unknown")

    def test_persist_refuses_a_non_succeeded_triage(self) -> None:
        with self.assertRaises(ValueError):
            expert.persist_expert_fields(
                alert_id="a", tenant_id="t", triage={"execution_status": "failed", "verdict": "BENIGN_FALSE_POSITIVE"}
            )


class JobRoutingTests(unittest.TestCase):
    """process_deep_triage_job: the case is always handed to the acceptance function.

    (Increment 2: acceptance is mocked here to check the routing decisions made by
    the job. Review/page policy outcomes are asserted against the real database
    transaction in test_tia_acceptance.py.)
    """

    BINDING = {"attempt_id": "att-1", "job_id": "a1:v1", "evidence_version": "v1", "tenant_id": "t1", "alert_id": "a1"}

    def run_job(self, *, reply=None, error=None, severity="high", tier1=None, env_extra=None, accept_status="accepted"):
        alert = {"id": "a1", "tenant_id": "t1", "severity": severity, "ai_triage_status": "", "asset_criticality": ""}
        env = {"SOC_AGENT_ENABLED": "true", "AI_DEEP_TRIAGE_ENABLED": "true", "SOC_AGENT_MIN_SEVERITY": "medium"}
        env.update(env_extra or {})
        with patch.dict(os.environ, env), patch.object(deep, "load_alert_for_triage", return_value=alert), patch.object(
            deep.tia_schema, "require_schema"
        ), patch.object(deep.acc, "open_attempt", return_value=dict(self.BINDING)), patch(
            "app.services.soc_agent_client.call_agent_ingest", side_effect=error, return_value=reply
        ) as call, patch.object(
            deep, "run_tier1_triage", return_value=tier1, side_effect=None if tier1 else RuntimeError("ollama down")
        ) as ollama, patch.object(
            deep.acc, "accept_result", return_value=deep.acc.AcceptanceResult(accept_status, "x", attempt_id="att-1")
        ) as accept, patch.object(
            deep.acc, "record_attempt_failure", return_value=deep.acc.AcceptanceResult("accepted", "failed")
        ) as failure, patch.object(deep.tia_outbox, "kick"):
            ok = deep.process_deep_triage_job(alert_id="a1", tenant_id="t1")
        return ok, call, ollama, accept, failure

    def test_transport_failures_are_recorded_for_every_severity(self) -> None:
        for sev in ("critical", "high", "medium"):
            for category, timed_out in (("auth_failure", False), ("timeout", True), ("agent_unreachable", False)):
                with self.subTest(sev=sev, category=category):
                    ok, _, _, accept, failure = self.run_job(error=AgentCallError(category, timed_out=timed_out), severity=sev)
                    failure.assert_called_once()
                    self.assertEqual(failure.call_args.kwargs["category"], category)
                    self.assertEqual(failure.call_args.kwargs["timed_out"], timed_out)
                    accept.assert_not_called()
                    # retry only transient infrastructure failures; the item is already durable
                    self.assertEqual(ok, category == "auth_failure")

    def test_the_attempt_binding_is_sent_to_the_agent(self) -> None:
        _, call, _, _, _ = self.run_job(reply=v2_success())
        self.assertEqual(call.call_args.args[1]["attempt_id"], "att-1")

    def test_audited_fixture_replay_goes_to_acceptance_as_a_failure(self) -> None:
        for sev in ("critical", "high", "medium"):
            ok, _, _, accept, failure = self.run_job(reply=audited_fixture(), severity=sev)
            self.assertTrue(ok)
            accept.assert_called_once()
            self.assertEqual(accept.call_args.kwargs["raw"]["verdict"], "Benign")  # raw is passed through to be re-validated
            failure.assert_not_called()

    def test_reply_binding_claims_are_forwarded_for_checking(self) -> None:
        reply = {**v2_success(), "tia_binding": {**self.BINDING, "tenant_id": "other-tenant"}}
        _, _, _, accept, _ = self.run_job(reply=reply)
        self.assertEqual(accept.call_args.kwargs["claimed_tenant_id"], "other-tenant")

    def test_a_reply_rejected_by_acceptance_becomes_a_failed_investigation(self) -> None:
        ok, _, _, accept, failure = self.run_job(reply=v2_success(), accept_status="rejected")
        accept.assert_called_once()
        self.assertEqual(failure.call_args.kwargs["category"], "invalid_agent_result")
        self.assertTrue(ok)

    def test_ollama_runs_only_after_failure_and_is_limited_evidence(self) -> None:
        tier1 = {
            "verdict": "BENIGN_FALSE_POSITIVE", "confidence": 95.0, "recommended_action": "AUTO_SUPPRESS",
            "model": "qwen2.5:7b", "execution_status": "degraded", "evidence_basis": "limited", "summary": "looks fine",
        }
        _, _, ollama, _, _ = self.run_job(reply=v2_success())
        ollama.assert_not_called()
        for sev in ("critical", "high", "medium"):
            _, _, ollama, accept, _ = self.run_job(reply=v2_failure("failed", "auth_failure"), severity=sev, tier1=tier1)
            self.assertTrue(ollama.call_args.kwargs["limited_evidence"], sev)
            self.assertIs(accept.call_args.kwargs["fallback"], tier1)

    def test_manual_review_mode_never_calls_a_model(self) -> None:
        ok, call, ollama, accept, failure = self.run_job(reply=v2_success(), env_extra={"TIA_INVESTIGATION_MODE": "manual_review"})
        call.assert_not_called()
        ollama.assert_not_called()
        accept.assert_not_called()
        self.assertEqual(failure.call_args.kwargs["category"], "manual_review_mode")
        self.assertTrue(ok)

    def test_missing_schema_stops_the_job_before_any_external_call(self) -> None:
        from app.services.tia_schema import SchemaNotReady

        alert = {"id": "a1", "tenant_id": "t1", "severity": "high", "ai_triage_status": ""}
        with patch.dict(os.environ, {"SOC_AGENT_ENABLED": "true", "SOC_AGENT_MIN_SEVERITY": "medium"}), patch.object(
            deep, "load_alert_for_triage", return_value=alert
        ), patch.object(deep.tia_schema, "require_schema", side_effect=SchemaNotReady(["tia_results"])), patch(
            "app.services.soc_agent_client.call_agent_ingest"
        ) as call:
            with self.assertRaises(SchemaNotReady):
                deep.process_deep_triage_job(alert_id="a1", tenant_id="t1")
        call.assert_not_called()


class QueueDropTests(unittest.TestCase):
    def test_deep_failure_is_not_hidden_by_a_successful_descriptive_stage(self) -> None:
        from app.services import ai_alert_queue as q

        with patch.object(q, "ai_alert_enabled", return_value=True), patch.object(
            q, "ai_soc_triage_enabled", return_value=False
        ), patch.object(q, "deep_triage_enabled", return_value=True), patch.object(
            q, "process_alert_job", return_value=True
        ), patch.object(q, "process_deep_triage_job", return_value=False):
            self.assertFalse(q._run_ai_pipeline("a", "t"))
        with patch.object(q, "ai_alert_enabled", return_value=True), patch.object(
            q, "ai_soc_triage_enabled", return_value=False
        ), patch.object(q, "deep_triage_enabled", return_value=True), patch.object(
            q, "process_alert_job", return_value=True
        ), patch.object(q, "process_deep_triage_job", side_effect=RuntimeError("x")):
            self.assertFalse(q._run_ai_pipeline("a", "t"))

    def test_dead_letter_records_a_review_item(self) -> None:
        from app.services import ai_alert_queue as q

        with patch("app.services.ai_deep_triage.record_dead_letter_review") as rec:
            q._review_for_dead_letter("a", "t", 4)
        rec.assert_called_once_with(alert_id="a", tenant_id="t", attempts=4)


class Tier1DegradedTests(unittest.TestCase):
    def test_rule_based_result_is_degraded_and_never_low_priority(self) -> None:
        from app.services import ai_tier1_triage as t1

        result = {"verdict": "BENIGN_FALSE_POSITIVE", "confidence": 86.0, "model": t1.RULE_BASED_MODEL}
        attached = t1._attach_enrichment(result, {})
        self.assertEqual(attached["execution_status"], "degraded")
        self.assertIsNone(attached["ai_queue"])

    def test_real_model_result_is_succeeded_and_can_queue(self) -> None:
        from app.services import ai_tier1_triage as t1

        attached = t1._attach_enrichment(
            {"verdict": "BENIGN_FALSE_POSITIVE", "confidence": 90.0, "model": "qwen2.5:7b"}, {}
        )
        self.assertEqual(attached["execution_status"], "succeeded")
        self.assertEqual(attached["ai_queue"], "low_priority")

    def test_secondary_path_is_limited_even_with_a_real_model(self) -> None:
        from app.services import ai_tier1_triage as t1

        attached = t1._attach_enrichment(
            {"verdict": "BENIGN_FALSE_POSITIVE", "confidence": 99.0, "model": "qwen2.5:7b"},
            {},
            limited_evidence=True,
        )
        self.assertEqual(attached["execution_status"], "degraded")
        self.assertIsNone(attached["ai_queue"])

    def test_auto_close_refuses_degraded_evidence_even_when_enabled(self) -> None:
        from app.services import ai_tier1_triage as t1

        with patch.object(t1, "_auto_close_enabled", return_value=True):
            out = t1._try_auto_close_low_risk(
                alert_id="a",
                tenant_id="t",
                alert={},
                enrichment={},
                result={"verdict": "BENIGN_FALSE_POSITIVE", "confidence": 99, "execution_status": "degraded"},
            )
        self.assertFalse(out["auto_closed"])
        self.assertEqual(out["reason"], "degraded_evidence")

    def test_degraded_benign_label_is_not_persisted(self) -> None:
        from app.services import ai_tier1_triage as t1

        with patch.object(t1, "fetch_one_write") as write:
            t1._persist_alert_ai_fields(
                alert_id="a", verdict="BENIGN_FALSE_POSITIVE", confidence=86.0, ai_queue=None, execution_status="degraded"
            )
            write.assert_not_called()
            t1._persist_alert_ai_fields(
                alert_id="a", verdict="SUSPICIOUS", confidence=52.0, ai_queue=None, execution_status="degraded"
            )
            write.assert_called_once()


def _postgres_ready() -> bool:
    try:
        from app.db.session import fetch_one

        row = fetch_one("SELECT to_regclass('public.tia_notifications') AS t;")
        return bool(row and row.get("t"))
    except Exception:
        return False


class ReviewItemDatabaseTests(unittest.TestCase):
    """Increment 1 database behaviours, now exercised through the unified acceptance."""

    TENANT = "bbbbbbbb-1111-2222-3333-444444444441"

    @classmethod
    def setUpClass(cls) -> None:
        import tia_testenv

        tia_testenv.require_database()
        from app.db.session import execute

        execute(
            "INSERT INTO tenants (id, name, short_code) VALUES (%s::uuid, 'TIA review test', 'TIAREV1') ON CONFLICT DO NOTHING;",
            (cls.TENANT,),
        )

    @classmethod
    def tearDownClass(cls) -> None:
        from app.db.session import execute

        execute("DELETE FROM tenants WHERE id = %s::uuid;", (cls.TENANT,))

    def setUp(self) -> None:
        from app.services import tia_schema

        tia_schema.reset_cache()

    def make_alert(self, severity="high") -> dict:
        from app.db.session import execute

        alert_id = str(uuid.uuid4())
        execute(
            """
            INSERT INTO security_alerts (id, tenant_id, source_tool, external_alert_id, severity, alert_title, event_time, status)
            VALUES (%s::uuid, %s::uuid, 'wazuh', %s, %s, 'synthetic', now(), 'new');
            """,
            (alert_id, self.TENANT, f"ext-{alert_id}", severity),
        )
        return {"id": alert_id, "tenant_id": self.TENANT, "severity": severity, "alert_title": "synthetic", "asset_criticality": ""}

    def routed(self, alert, status="failed", category="auth_failure", roster=""):
        from app.services import tia_acceptance as acc

        att = acc.open_attempt(alert_id=alert["id"], tenant_id=self.TENANT)
        with patch.dict(os.environ, {"SOC_ONCALL_WHATSAPP": roster}):
            return acc.accept_result(source="http", attempt_id=att["attempt_id"], raw=v2_failure(status, category))

    def test_failure_leaves_a_durable_item_and_alert_stays_actionable(self) -> None:
        from app.db.session import fetch_one

        for sev in ("critical", "high", "medium"):
            alert = self.make_alert(sev)
            routed = self.routed(alert)
            self.assertIsNotNone(routed.review_item_id)
            item = fetch_one("SELECT * FROM tia_review_items WHERE alert_id = %s::uuid;", (alert["id"],))
            self.assertEqual(item["status"], "open")
            self.assertEqual(item["execution_status"], "failed")
            self.assertEqual(item["source_severity"], sev)
            self.assertEqual(item["notify_urgency"], "page" if sev == "critical" else "queue")
            row = fetch_one("SELECT status, ai_verdict, ai_queue, ai_auto_closed FROM security_alerts WHERE id = %s::uuid;", (alert["id"],))
            self.assertEqual(row["status"], "new")
            self.assertIsNone(row["ai_verdict"])
            self.assertIsNone(row["ai_queue"])
            self.assertFalse(row["ai_auto_closed"])
            if sev == "critical":
                # on-call roster is empty: the page is not silently lost
                self.assertEqual(item["notification_state"], "no_recipients_configured")

    def test_review_item_is_idempotent_across_retries(self) -> None:
        from app.db.session import fetch_one

        alert = self.make_alert("medium")
        for _ in range(3):
            self.routed(alert, "timed_out", "timeout")
        item = fetch_one("SELECT count(*) OVER () AS n, occurrences, execution_status FROM tia_review_items WHERE alert_id = %s::uuid;", (alert["id"],))
        self.assertEqual(item["n"], 1)
        self.assertEqual(item["occurrences"], 3)
        self.assertEqual(item["execution_status"], "timed_out")

    def test_success_never_auto_resolves_a_failure_item(self) -> None:
        """Changed in increment 2: increment 1 resolved the item on success; a person must now do it."""
        from app.db.session import fetch_one
        from app.services import tia_acceptance as acc

        alert = self.make_alert("high")
        self.routed(alert)
        att = acc.open_attempt(alert_id=alert["id"], tenant_id=self.TENANT)
        res = acc.accept_result(source="http", attempt_id=att["attempt_id"], raw=v2_success())
        self.assertEqual(res.status, "accepted")
        item = fetch_one("SELECT status, analysis_available FROM tia_review_items WHERE alert_id = %s::uuid;", (alert["id"],))
        self.assertEqual(item["status"], "open")
        self.assertTrue(item["analysis_available"])

    def test_page_is_queued_once_even_with_two_paths(self) -> None:
        from app.db.session import fetch_all
        from app.services import tia_acceptance as acc

        alert = self.make_alert("critical")
        att = acc.open_attempt(alert_id=alert["id"], tenant_id=self.TENANT)
        with patch.dict(os.environ, {"SOC_ONCALL_WHATSAPP": "+15550000000"}):
            acc.accept_result(source="http", attempt_id=att["attempt_id"], raw=v2_failure("failed", "auth_failure"))
            acc.accept_result(source="callback", attempt_id=att["attempt_id"], raw=v2_failure("failed", "auth_failure"))
        rows = fetch_all("SELECT message_body, state FROM tia_notifications WHERE alert_id = %s::uuid AND kind = 'page';", (alert["id"],))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["state"], "required")
        self.assertIn("no verdict", rows[0]["message_body"])

    def test_callback_path_routes_failures_and_never_persists_a_verdict(self) -> None:
        from app.db.session import fetch_one
        from app.services import tia_acceptance as acc

        alert = self.make_alert("high")
        att = acc.open_attempt(alert_id=alert["id"], tenant_id=self.TENANT)
        result = acc.accept_result(source="callback", attempt_id=att["attempt_id"], raw=audited_fixture())
        self.assertEqual(result.status, "accepted")
        self.assertFalse(result.applied)
        row = fetch_one("SELECT ai_verdict, ai_triage_status, ai_queue FROM security_alerts WHERE id = %s::uuid;", (alert["id"],))
        self.assertIsNone(row["ai_verdict"])
        self.assertIsNone(row["ai_triage_status"])
        self.assertIsNone(row["ai_queue"])
        item = fetch_one("SELECT reason_code, error_category FROM tia_review_items WHERE alert_id = %s::uuid;", (alert["id"],))
        self.assertEqual(item["error_category"], "legacy_heuristic_fallback")


if __name__ == "__main__":
    unittest.main()
