"""KB-115 Step 7: Sovereign multihost cluster tests."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "kevantic-appliance" / "appliance"))

from sovereign import cluster  # noqa: E402


class SovereignMultihostClusterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = ROOT / "backend-api" / ".tmp_test_multihost"
        self.tmp.mkdir(parents=True, exist_ok=True)
        self.bus = self.tmp / "bus"
        self.state = self.tmp / "state"
        self.state.mkdir(parents=True, exist_ok=True)
        self.env = patch.dict(
            "os.environ",
            {
                "SOVEREIGN_CLUSTER_DIR": str(self.bus),
                "SOVEREIGN_CLUSTER_TOPOLOGY": "multihost",
                "JUNEXIS_STATE_DIR": str(self.state),
            },
            clear=False,
        )
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()

    def test_bootstrap_multihost(self):
        meta = cluster.bootstrap_multihost(
            node_id="a",
            local_host="192.168.0.227",
            peer_node_id="b",
            peer_host="192.168.0.228",
        )
        self.assertEqual(meta["topology"], "multihost")
        status = cluster.cluster_status("a")
        self.assertEqual(status["topology"], "multihost")
        self.assertTrue(status["paired"])

    def test_active_endpoint_uses_peer_host(self):
        cluster.bootstrap_multihost(
            node_id="a",
            local_host="192.168.0.227",
            peer_node_id="b",
            peer_host="192.168.0.228",
        )
        cluster.record_heartbeat("b")
        cluster.apply_remote_heartbeat("b", int(__import__("time").time()))
        ep = cluster.active_api_endpoint()
        self.assertIn("192.168.0.228", ep)

    @patch("sovereign.cluster._peer_request")
    def test_publish_replicates_to_peer(self, mock_peer):
        cluster.bootstrap_multihost(
            node_id="a",
            local_host="10.0.0.1",
            peer_node_id="b",
            peer_host="10.0.0.2",
        )
        cluster.record_heartbeat("a")
        marker = "mh-marker"
        ent = self.state / "entitlements.json"
        ent.write_text(json.dumps({"cluster_write_marker": marker}) + "\n", encoding="utf-8")
        mock_peer.return_value = {"ok": True, "bytes": 10}
        pub = cluster.publish_artifacts("a")
        self.assertTrue(pub["ok"])
        self.assertIn("replicate", pub)
        mock_peer.assert_called()


if __name__ == "__main__":
    unittest.main()
