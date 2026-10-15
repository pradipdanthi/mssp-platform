"""KB-116: deterministic human-escalation rules for autonomous deep triage."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.services import ai_deep_triage as deep


def _triage(verdict: str, confidence: float, action: str = "INVESTIGATE_HOST", model: str = "qwen2.5:7b"):
    return {"verdict": verdict, "confidence": confidence, "recommended_action": action, "model": model}


def _alert(severity: str, asset_criticality: str = "") -> dict:
    return {"severity": severity, "asset_criticality": asset_criticality}


@patch.dict(os.environ, {}, clear=False)
class DecideEscalationTests(unittest.TestCase):
    def test_malicious_above_floor_pages_high(self) -> None:
        d = deep.decide_escalation(_alert("high"), _triage("MALICIOUS", 80))
        self.assertTrue(d["escalate"])
        self.assertEqual(d["urgency"], "high")

    def test_malicious_below_floor_on_high_stays_quiet(self) -> None:
        d = deep.decide_escalation(_alert("high"), _triage("MALICIOUS", 40))
        self.assertFalse(d["escalate"])

    def test_isolate_recommendation_always_pages(self) -> None:
        d = deep.decide_escalation(_alert("high"), _triage("SUSPICIOUS", 50, action="ISOLATE_AGENT"))
        self.assertTrue(d["escalate"])
        self.assertEqual(d["urgency"], "high")

    def test_suspicious_on_critical_pages(self) -> None:
        d = deep.decide_escalation(_alert("critical"), _triage("SUSPICIOUS", 55))
        self.assertTrue(d["escalate"])

    def test_suspicious_on_high_stays_quiet(self) -> None:
        d = deep.decide_escalation(_alert("high"), _triage("SUSPICIOUS", 55))
        self.assertFalse(d["escalate"])

    def test_degraded_model_on_critical_fails_toward_human(self) -> None:
        d = deep.decide_escalation(_alert("critical"), _triage("SUSPICIOUS", 52, model="rule_based_fallback"))
        self.assertTrue(d["escalate"])
        self.assertTrue(d["degraded"])
        self.assertEqual(d["urgency"], "high")

    def test_unsure_benign_on_critical_pages_normal(self) -> None:
        d = deep.decide_escalation(_alert("critical"), _triage("BENIGN_FALSE_POSITIVE", 70))
        self.assertTrue(d["escalate"])
        self.assertEqual(d["urgency"], "normal")

    def test_confident_benign_on_critical_stays_quiet(self) -> None:
        d = deep.decide_escalation(_alert("critical"), _triage("BENIGN_FALSE_POSITIVE", 90))
        self.assertFalse(d["escalate"])

    def test_benign_on_high_stays_quiet(self) -> None:
        d = deep.decide_escalation(_alert("high"), _triage("BENIGN_FALSE_POSITIVE", 60))
        self.assertFalse(d["escalate"])

    def test_critical_asset_raises_urgency(self) -> None:
        d = deep.decide_escalation(_alert("critical", "critical"), _triage("SUSPICIOUS", 55))
        self.assertEqual(d["urgency"], "high")

    def test_benign_silence_floor_is_configurable(self) -> None:
        with patch.dict(os.environ, {"AI_DEEP_TRIAGE_BENIGN_SILENCE_CONFIDENCE": "60"}):
            d = deep.decide_escalation(_alert("critical"), _triage("BENIGN_FALSE_POSITIVE", 70))
        self.assertFalse(d["escalate"])


class TimeoutBudgetTests(unittest.TestCase):
    def test_default_background_budget(self) -> None:
        with patch.dict(os.environ, {"AI_DEEP_TRIAGE_TIMEOUT_SECONDS": ""}):
            self.assertEqual(deep._llm_timeout_seconds(), 180.0)

    def test_budget_is_clamped(self) -> None:
        with patch.dict(os.environ, {"AI_DEEP_TRIAGE_TIMEOUT_SECONDS": "5000"}):
            self.assertEqual(deep._llm_timeout_seconds(), 600.0)


class CachedFallbackRetryTests(unittest.TestCase):
    def test_cached_rule_based_result_is_recomputed_with_model(self) -> None:
        alert = {"severity": "critical", "ai_triage_status": ""}
        cached_fallback = dict(_triage("SUSPICIOUS", 52, model="rule_based_fallback"), cached=True)
        fresh = _triage("BENIGN_FALSE_POSITIVE", 92)
        with patch.dict(os.environ, {"AI_DEEP_TRIAGE_ENABLED": "true"}), \
             patch.object(deep, "load_alert_for_triage", return_value=alert), \
             patch.object(deep, "run_tier1_triage", side_effect=[cached_fallback, fresh]) as run:
            self.assertTrue(deep.process_deep_triage_job(alert_id="a", tenant_id="t"))
        self.assertEqual(run.call_count, 2)
        self.assertTrue(run.call_args_list[1].kwargs["force"])
        self.assertEqual(run.call_args_list[1].kwargs["llm_timeout_seconds"], 180.0)


if __name__ == "__main__":
    unittest.main()
