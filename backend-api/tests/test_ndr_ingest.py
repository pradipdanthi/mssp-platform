"""Phase 1: NDR source_tool tagging and production seed gating."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.api.routes.soc_sync import detect_ingress_source_tool
from app.services import ndr_service


class DetectIngressSourceToolTests(unittest.TestCase):
    def test_suricata_from_rule_groups(self):
        raw = {
            "rule": {"id": "86601", "groups": ["suricata", "ids"]},
            "agent": {"id": "002", "name": "suricata-sensor"},
            "location": "/var/log/suricata/eve.json",
        }
        self.assertEqual(detect_ingress_source_tool(raw), "suricata")

    def test_suricata_from_data_integration(self):
        raw = {
            "rule": {"id": "100001"},
            "data": {"integration": "suricata"},
            "full_log": '{"event_type":"alert"}',
        }
        self.assertEqual(detect_ingress_source_tool(raw), "suricata")

    def test_zeek_from_rule_groups(self):
        raw = {
            "rule": {"id": "50001", "groups": ["zeek", "notice"]},
            "location": "/opt/zeek-logs/current/notice.log",
            "full_log": "Notice::ACTION_LOG",
        }
        self.assertEqual(detect_ingress_source_tool(raw), "zeek")

    def test_zeek_from_decoder_name(self):
        raw = {
            "decoder": {"name": "zeek-json"},
            "rule": {"id": "50002"},
        }
        self.assertEqual(detect_ingress_source_tool(raw), "zeek")

    def test_wazuh_fallback_for_endpoint_alert(self):
        raw = {
            "rule": {
                "id": "92213",
                "groups": ["windows", "sysmon"],
                "description": "Suspicious PowerShell script",
            },
            "agent": {"id": "003", "name": "WIN-TEST"},
            "data": {"win": {"system": {"eventID": "1"}}},
            "location": "EventChannel",
        }
        self.assertEqual(detect_ingress_source_tool(raw), "wazuh")

    def test_suricata_takes_precedence_when_both_markers_present(self):
        raw = {
            "rule": {"groups": ["suricata", "zeek-hybrid"]},
            "data": {"integration": "zeek"},
        }
        self.assertEqual(detect_ingress_source_tool(raw), "suricata")


class NdrProductionSeedGatingTests(unittest.TestCase):
    def test_allow_lab_sample_seed_false_in_production(self):
        with patch.dict(os.environ, {"APP_ENV": "production"}, clear=False):
            self.assertFalse(ndr_service._allow_lab_sample_seed())

    def test_allow_lab_sample_seed_true_in_lab(self):
        with patch.dict(
            os.environ,
            {"APP_ENV": "lab", "NDR_ALLOW_SAMPLE_ADAPTER": ""},
            clear=False,
        ):
            self.assertTrue(ndr_service._allow_lab_sample_seed())

    @patch("app.services.ndr_service._seed_sample_events")
    @patch("app.services.ndr_service._import_from_alerts", return_value=0)
    @patch("app.services.ndr_service._ensure_default_sensor")
    @patch("app.services.ndr_service.execute")
    @patch("app.services.ndr_service._enable_entitlement")
    @patch("app.services.ndr_service.get_summary", return_value={"open_events": 0})
    def test_sync_skips_synthetic_seed_in_production(
        self,
        _mock_summary,
        _mock_ent,
        _mock_execute,
        mock_sensor,
        mock_import,
        mock_seed,
    ):
        mock_sensor.return_value = {"id": "sensor-1"}
        with patch.dict(os.environ, {"APP_ENV": "production"}, clear=False):
            result = ndr_service.sync_tenant_ndr("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        mock_seed.assert_not_called()
        self.assertEqual(result["source"], "live_alerts")
        self.assertEqual(result["events_created"], 0)

    @patch("app.services.ndr_service._seed_sample_events", return_value=6)
    @patch("app.services.ndr_service._import_from_alerts", return_value=0)
    @patch("app.services.ndr_service._ensure_default_sensor")
    @patch("app.services.ndr_service.execute")
    @patch("app.services.ndr_service._enable_entitlement")
    @patch("app.services.ndr_service.get_summary", return_value={"open_events": 6})
    def test_sync_seeds_synthetic_events_in_lab(
        self,
        _mock_summary,
        _mock_ent,
        _mock_execute,
        mock_sensor,
        mock_import,
        mock_seed,
    ):
        mock_sensor.return_value = {"id": "sensor-1"}
        with patch.dict(os.environ, {"APP_ENV": "lab"}, clear=False):
            result = ndr_service.sync_tenant_ndr("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        mock_seed.assert_called_once()
        self.assertEqual(result["source"], "analysis_adapter")
        self.assertEqual(result["events_created"], 6)


class ImportFromAlertsQueryTests(unittest.TestCase):
    @patch("app.services.ndr_service.fetch_all", return_value=[])
    def test_import_queries_only_suricata_and_zeek_source_tools(self, mock_fetch):
        ndr_service._import_from_alerts("tenant-1", "sensor-1")
        sql = mock_fetch.call_args[0][0]
        self.assertIn("lower(coalesce(source_tool, '')) IN ('suricata', 'zeek')", sql)
        self.assertNotIn("LIKE '%%dns%%'", sql)


if __name__ == "__main__":
    unittest.main()
