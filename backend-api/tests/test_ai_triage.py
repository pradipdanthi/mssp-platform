"""Phase 4: pre-LLM whitelist veto and Ollama health failover."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from app.services import ai_tier1_triage as triage

ALERT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
TENANT_ID = "11111111-2222-3333-4444-555555555555"

BASE_ALERT = {
    "id": ALERT_ID,
    "tenant_id": TENANT_ID,
    "alert_title": "Sysmon - Suspicious Process - svchost.exe",
    "severity": "low",
    "wazuh_rule_id": "92000",
    "process_name": "C:\\Windows\\System32\\svchost.exe",
    "file_path": "C:\\Windows\\System32\\svchost.exe",
    "source_user": "NT AUTHORITY\\SYSTEM",
    "destination_host": "workstation01",
    "event_time": "2026-08-28T12:00:00+00:00",
    "status": "new",
}

BASE_ENRICHMENT = {
    "pre_score_hints": {
        "path_temp_or_userprofile": False,
        "known_windows_binary_unexpected_path": False,
        "encoded_powershell_or_cmdline_red_flags": False,
        "admin_user_signal": True,
        "flags": ["admin_user_signal"],
    },
    "threat_intel": {"hit": False, "external_vt": {"status": "not_configured"}},
    "signature": {"status": "likely_signed_path", "source": "path_hint"},
    "user_context": {"admin_activity_signals": ["builtin_system_principal"]},
    "prior_false_positives": {
        "prior_fp_same_rule": 2,
        "prior_fp_host_title": 1,
        "count": 2,
    },
    "active_suppressions": {"match": True, "count": 1},
    "action_guardrails": {
        "prefer_recommended_action": "AUTO_SUPPRESS",
        "action_rationale": "Strong FP history",
        "historical_fp_pressure": "high",
    },
    "context_summary": {},
}


class PreLlmVetoTests(unittest.TestCase):
    def test_known_fp_pattern_triggers_deterministic_veto(self):
        veto = triage.check_pre_llm_whitelist_veto(BASE_ALERT, BASE_ENRICHMENT)
        self.assertIsNotNone(veto)
        self.assertEqual(veto["verdict"], "BENIGN_FALSE_POSITIVE")
        self.assertEqual(veto["confidence"], 100.0)
        self.assertIn("Pre-LLM Deterministic Whitelist Match", veto["summary"])
        self.assertTrue(veto.get("pre_llm_veto"))

    def test_trusted_sha256_triggers_veto(self):
        trusted = "a" * 64
        with patch.dict(os.environ, {"AI_TIER1_TRUSTED_SHA256": trusted}, clear=False):
            alert = {
                **BASE_ALERT,
                "hash_sha256": trusted,
            }
            enrichment = {
                **BASE_ENRICHMENT,
                "prior_false_positives": {"prior_fp_same_rule": 0, "count": 0},
                "active_suppressions": {"match": False, "count": 0},
            }
            veto = triage.check_pre_llm_whitelist_veto(alert, enrichment)
        self.assertIsNotNone(veto)
        self.assertEqual(veto["verdict"], "BENIGN_FALSE_POSITIVE")

    def test_high_risk_hints_block_veto(self):
        enrichment = {
            **BASE_ENRICHMENT,
            "pre_score_hints": {
                **BASE_ENRICHMENT["pre_score_hints"],
                "encoded_powershell_or_cmdline_red_flags": True,
            },
        }
        self.assertIsNone(triage.check_pre_llm_whitelist_veto(BASE_ALERT, enrichment))


class RunTier1TriageFlowTests(unittest.TestCase):
    @patch("app.services.ai_tier1_triage._try_auto_close_low_risk", return_value={"auto_closed": False})
    @patch("app.services.ai_tier1_triage._persist_alert_ai_fields")
    @patch("app.services.ai_tier1_triage._write_cache")
    @patch("app.services.ai_tier1_triage.get_cached_triage", return_value=None)
    @patch("app.services.ai_tier1_triage.enrich_alert_context", return_value=BASE_ENRICHMENT)
    @patch("app.services.ai_tier1_triage.build_triage_payload_from_alert")
    @patch("app.services.ai_tier1_triage.probe_ollama_health")
    @patch("app.services.ai_tier1_triage._call_ollama_chat")
    def test_veto_skips_ollama_network_call(
        self,
        mock_ollama,
        mock_probe,
        mock_payload,
        _mock_enrich,
        _mock_cache,
        _mock_write,
        _mock_persist,
        _mock_auto,
    ):
        mock_payload.return_value = {"wazuh_rule_id": "92000", "process_name": "svchost.exe"}
        result = triage.run_tier1_triage(
            alert_id=ALERT_ID,
            tenant_id=TENANT_ID,
            alert=BASE_ALERT,
            force=True,
        )
        mock_ollama.assert_not_called()
        mock_probe.assert_not_called()
        self.assertEqual(result["verdict"], "BENIGN_FALSE_POSITIVE")
        self.assertEqual(result["confidence"], 100.0)
        self.assertTrue(result.get("pre_llm_veto"))

    @patch("app.services.ai_tier1_triage._try_auto_close_low_risk", return_value={"auto_closed": False})
    @patch("app.services.ai_tier1_triage._persist_alert_ai_fields")
    @patch("app.services.ai_tier1_triage._write_cache")
    @patch("app.services.ai_tier1_triage.get_cached_triage", return_value=None)
    @patch("app.services.ai_tier1_triage.enrich_alert_context")
    @patch("app.services.ai_tier1_triage.build_triage_payload_from_alert")
    @patch("app.services.ai_tier1_triage.probe_ollama_health", return_value=False)
    @patch("app.services.ai_tier1_triage._call_ollama_chat")
    def test_unreachable_ollama_falls_back_without_crash(
        self,
        mock_ollama,
        _mock_probe,
        mock_payload,
        mock_enrich,
        _mock_cache,
        _mock_write,
        _mock_persist,
        _mock_auto,
    ):
        mock_payload.return_value = {"wazuh_rule_id": "99999", "process_name": "unknown.exe"}
        mock_enrich.return_value = {
            **BASE_ENRICHMENT,
            "pre_score_hints": {
                "path_temp_or_userprofile": True,
                "known_windows_binary_unexpected_path": False,
                "encoded_powershell_or_cmdline_red_flags": False,
                "flags": ["path_temp_or_userprofile"],
            },
            "prior_false_positives": {"prior_fp_same_rule": 0, "count": 0},
            "active_suppressions": {"match": False, "count": 0},
            "signature": {"status": "unknown"},
            "user_context": {"admin_activity_signals": []},
        }
        result = triage.run_tier1_triage(
            alert_id=ALERT_ID,
            tenant_id=TENANT_ID,
            alert={**BASE_ALERT, "process_name": "C:\\Users\\x\\Temp\\evil.exe"},
            force=True,
        )
        mock_ollama.assert_not_called()
        self.assertTrue(result.get("rule_based_fallback"))
        self.assertIn(result["verdict"], triage.VERDICTS)

    @patch("app.services.ai_tier1_triage._try_auto_close_low_risk", return_value={"auto_closed": False})
    @patch("app.services.ai_tier1_triage._persist_alert_ai_fields")
    @patch("app.services.ai_tier1_triage._write_cache")
    @patch("app.services.ai_tier1_triage.get_cached_triage", return_value=None)
    @patch("app.services.ai_tier1_triage.enrich_alert_context")
    @patch("app.services.ai_tier1_triage.build_triage_payload_from_alert")
    @patch("app.services.ai_tier1_triage.probe_ollama_health", return_value=True)
    @patch("app.services.ai_tier1_triage._call_ollama_chat")
    def test_unknown_alert_dispatches_to_ollama_when_healthy(
        self,
        mock_ollama,
        _mock_probe,
        mock_payload,
        mock_enrich,
        _mock_cache,
        _mock_write,
        _mock_persist,
        _mock_auto,
    ):
        mock_payload.return_value = {"wazuh_rule_id": "99999", "process_name": "unknown.exe"}
        mock_enrich.return_value = {
            **BASE_ENRICHMENT,
            "pre_score_hints": {
                "path_temp_or_userprofile": False,
                "known_windows_binary_unexpected_path": False,
                "encoded_powershell_or_cmdline_red_flags": False,
                "flags": [],
            },
            "prior_false_positives": {"prior_fp_same_rule": 0, "count": 0},
            "active_suppressions": {"match": False, "count": 0},
            "signature": {"status": "unknown"},
            "user_context": {"admin_activity_signals": []},
        }
        mock_ollama.return_value = (
            {
                "verdict": "SUSPICIOUS",
                "confidence": 70,
                "summary": "Needs analyst review.",
                "recommended_action": "INVESTIGATE_HOST",
                "suggested_suppression_scope": {
                    "rule_id": "99999",
                    "process_path": "",
                    "justification": "test",
                },
            },
            {"model": "qwen2.5:7b", "ollama_raw": {}, "duration_ms": 12},
        )
        result = triage.run_tier1_triage(
            alert_id=ALERT_ID,
            tenant_id=TENANT_ID,
            alert={**BASE_ALERT, "alert_title": "Unknown malware beacon"},
            force=True,
        )
        mock_ollama.assert_called_once()
        self.assertEqual(result["verdict"], "SUSPICIOUS")
        self.assertEqual(result["model"], "qwen2.5:7b")
        self.assertFalse(result.get("rule_based_fallback"))


if __name__ == "__main__":
    unittest.main()
