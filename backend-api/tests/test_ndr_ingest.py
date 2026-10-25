"""Phase 1: NDR source_tool tagging and production seed gating."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.api.routes import soc_sync
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


SURICATA_ALERT = {
    "id": "1792042795.123",
    "rule": {
        "id": "100611",
        "level": 10,
        "groups": ["ids", "suricata"],
        "description": "Suricata: ET ADWARE_PUP W32/SpeedRunner User-Agent SRRemove",
    },
    "agent": {"id": "002", "name": "suricata-sensor", "ip": "192.168.0.216"},
    "data": {"src_ip": "192.168.0.215", "dest_ip": "172.66.147.243", "alert": {"severity": 2}},
    "location": "/var/log/suricata/eve.json",
}


@patch.dict(os.environ, {"WAZUH_DEFAULT_TENANT_SHORT_CODE": ""}, clear=False)
@patch("app.services.wazuh_client.credentials_configured", return_value=False)
@patch("app.services.tenant_engine_provisioner.resolve_short_code_by_wazuh_group", return_value=None)
class NdrAssetIpAttributionTests(unittest.TestCase):
    @patch("app.api.routes.soc_sync.fetch_all")
    def test_unbound_sensor_attributed_by_monitored_asset_ip(self, mock_fetch, *_):
        mock_fetch.side_effect = [[{"short_code": "BETAWINCORP-J3FW", "hostname": "linux-endpoint-lab"}]]
        req = soc_sync._normalize_wazuh_alert(SURICATA_ALERT)
        self.assertEqual(req.tenant_short_code, "BETAWINCORP-J3FW")
        self.assertEqual(req.source_tool, "suricata")
        self.assertEqual(req.destination_host, "linux-endpoint-lab")
        self.assertEqual(req.source_ip, "192.168.0.215")
        self.assertEqual(req.destination_ip, "172.66.147.243")

    @patch("app.api.routes.soc_sync.fetch_all")
    def test_ip_owned_by_two_tenants_fails_closed(self, mock_fetch, *_):
        mock_fetch.side_effect = [
            [{"short_code": "A-1", "hostname": "h1"}, {"short_code": "B-2", "hostname": "h2"}],
            [],
        ]
        with self.assertRaises(ValueError):
            soc_sync._normalize_wazuh_alert(SURICATA_ALERT)

    @patch("app.api.routes.soc_sync.fetch_all", return_value=[])
    def test_unknown_ip_fails_closed(self, *_):
        with self.assertRaises(ValueError):
            soc_sync._normalize_wazuh_alert(SURICATA_ALERT)

    @patch("app.api.routes.soc_sync.fetch_all")
    def test_zeek_notice_src_dst_fields_attribute_tenant(self, mock_fetch, *_):
        mock_fetch.side_effect = [
            [],  # src 192.168.0.1 unknown
            [{"short_code": "BETAWINCORP-J3FW", "hostname": "linux-endpoint-lab", "ip": "192.168.0.215"}],
        ]
        raw = {
            "rule": {
                "id": "100710",
                "level": 12,
                "groups": ["zeek", "ids", "mssp_ndr"],
                "description": "Zeek high: SSH::Password_Guessing",
            },
            "agent": {"id": "002", "name": "suricata-sensor", "ip": "192.168.0.216"},
            "location": "/opt/zeek-logs/current/notice.log",
            "data": {
                "note": "SSH::Password_Guessing",
                "msg": "lab",
                "src": "192.168.0.1",
                "dst": "192.168.0.215",
            },
        }
        req = soc_sync._normalize_wazuh_alert(raw)
        self.assertEqual(req.tenant_short_code, "BETAWINCORP-J3FW")
        self.assertEqual(req.source_tool, "zeek")
        self.assertEqual(req.source_ip, "192.168.0.1")
        self.assertEqual(req.destination_ip, "192.168.0.215")
        self.assertEqual(req.destination_host, "linux-endpoint-lab")

    @patch("app.api.routes.soc_sync.fetch_all")
    def test_endpoint_alerts_never_use_ip_attribution(self, mock_fetch, *_):
        raw = {
            "rule": {"id": "5712", "level": 10, "groups": ["sshd"], "description": "sshd brute force"},
            "agent": {"id": "000", "name": "wazuh-stack"},
            "data": {"src_ip": "192.168.0.215"},
        }
        with self.assertRaises(ValueError):
            soc_sync._normalize_wazuh_alert(raw)
        mock_fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
