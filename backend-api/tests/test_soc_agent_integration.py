"""KB-117: SOC agent client mapping + soft-fail + action package."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from app.services import soc_agent_client as client
from app.services import soc_agent_expert as expert


class ClientFlagTests(unittest.TestCase):
    def test_disabled_by_default(self) -> None:
        with patch.dict(os.environ, {"SOC_AGENT_ENABLED": ""}, clear=False):
            self.assertFalse(client.soc_agent_enabled())

    def test_severity_threshold_default_medium(self) -> None:
        with patch.dict(os.environ, {"SOC_AGENT_MIN_SEVERITY": "medium"}, clear=False):
            self.assertTrue(client.severity_meets_agent_threshold("medium"))
            self.assertFalse(client.severity_meets_agent_threshold("low"))


class MappingTests(unittest.TestCase):
    def test_verdict_map(self) -> None:
        self.assertEqual(expert.map_agent_verdict("Critical"), "MALICIOUS")
        self.assertEqual(expert.map_agent_verdict("Suspicious"), "SUSPICIOUS")
        self.assertEqual(expert.map_agent_verdict("Benign"), "BENIGN_FALSE_POSITIVE")

    def test_action_package_isolate_maps_to_isolate_agent(self) -> None:
        result = {
            "ok": True,
            "llm": {
                "verdict": "Critical",
                "confidence": 88,
                "summary": "Host compromise likely",
                "recommended_actions": ["Isolate host", "Collect memory"],
                "escalate_to_human": True,
                "action_package": {
                    "propose_edr_isolate": True,
                    "propose_itdr_remediate": False,
                    "propose_customer_recommendation": True,
                    "escalate_human": True,
                    "customer_action_title": "Review isolated endpoint",
                    "customer_action_body": "Please confirm business impact.",
                },
            },
        }
        triage = expert.agent_result_to_triage(result)
        self.assertEqual(triage["verdict"], "MALICIOUS")
        self.assertEqual(triage["recommended_action"], "ISOLATE_AGENT")
        self.assertTrue(triage["action_package"]["propose_edr_isolate"])
        self.assertIn("PROPOSED", triage["containment_suggestion"] or "")


class SoftFailTests(unittest.TestCase):
    def test_forward_returns_none_when_disabled(self) -> None:
        with patch.dict(os.environ, {"SOC_AGENT_ENABLED": "false"}, clear=False):
            self.assertIsNone(
                client.forward_alert_for_expert_triage(
                    {"id": "a", "severity": "high", "alert_title": "t"}
                )
            )

    def test_forward_soft_fails_on_network(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SOC_AGENT_ENABLED": "true",
                "SOC_AGENT_TOKEN": "tok",
                "SOC_AGENT_URL": "http://127.0.0.1:9",
                "SOC_AGENT_TIMEOUT_SECONDS": "1",
            },
            clear=False,
        ):
            out = client.forward_alert_for_expert_triage(
                {"id": "a", "severity": "high", "alert_title": "t"}
            )
            self.assertIsNone(out)


class DeepTriagePrefersAgentTests(unittest.TestCase):
    def test_agent_success_skips_ollama(self) -> None:
        from app.services import ai_deep_triage as deep

        alert = {
            "id": "a",
            "tenant_id": "t",
            "severity": "high",
            "ai_triage_status": "",
            "alert_title": "x",
        }
        triage = {
            "verdict": "MALICIOUS",
            "confidence": 90,
            "recommended_action": "INVESTIGATE_HOST",
            "model": "cursor-agent",
            "execution_status": "succeeded",
        }
        with patch.dict(
            os.environ,
            {"SOC_AGENT_ENABLED": "true", "AI_DEEP_TRIAGE_ENABLED": "true"},
            clear=False,
        ), patch.object(deep, "load_alert_for_triage", return_value=alert), patch.object(
            deep.tia_schema, "require_schema"
        ), patch.object(deep, "_investigate_with_agent", return_value=True) as expert_run, patch.object(
            deep, "run_tier1_triage"
        ) as ollama:
            self.assertTrue(deep.process_deep_triage_job(alert_id="a", tenant_id="t"))
        expert_run.assert_called_once()
        ollama.assert_not_called()


class EdgePromoteHintTests(unittest.TestCase):
    def test_waf_block_promotes(self) -> None:
        from app.api.routes.secure_edge import _edge_event_should_promote

        self.assertTrue(
            _edge_event_should_promote(
                {"severity": "info", "event_type": "waf_block", "summary": "blocked"}
            )
        )
        self.assertTrue(
            _edge_event_should_promote({"severity": "critical", "event_type": "other"})
        )
        self.assertFalse(
            _edge_event_should_promote(
                {"severity": "info", "event_type": "heartbeat", "summary": "ok"}
            )
        )


if __name__ == "__main__":
    unittest.main()
