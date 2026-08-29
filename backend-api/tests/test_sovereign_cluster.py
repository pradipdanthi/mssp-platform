"""KB-113 Step 5: Sovereign logical cluster unit tests."""

from __future__ import annotations

import json
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "kevantic-appliance" / "appliance"))

from sovereign import cluster  # noqa: E402


class SovereignClusterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = ROOT / "backend-api" / ".tmp_test_cluster"
        self.tmp.mkdir(parents=True, exist_ok=True)
        self.bus = self.tmp / "bus"
        self.bus.mkdir(parents=True, exist_ok=True)
        self.env = patch.dict(
            "os.environ",
            {
                "SOVEREIGN_CLUSTER_DIR": str(self.bus),
                "SOVEREIGN_NODE_A_STATE_DIR": str(self.tmp / "a"),
                "SOVEREIGN_NODE_B_STATE_DIR": str(self.tmp / "b"),
            },
            clear=False,
        )
        self.env.start()
        (self.tmp / "a").mkdir(parents=True, exist_ok=True)
        (self.tmp / "b").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.env.stop()

    def test_bootstrap_pair(self):
        meta = cluster.bootstrap_pair()
        self.assertEqual(meta["profile"], "sovereign_edge_logical_ha")
        self.assertIn("a", meta["nodes"])
        self.assertIn("b", meta["nodes"])
        status = cluster.cluster_status()
        self.assertTrue(status["paired"])

    def test_publish_and_sync(self):
        cluster.bootstrap_pair()
        cluster.record_heartbeat("a")
        cluster.record_heartbeat("b")
        marker = "unit-test-marker"
        ent = self.tmp / "a" / "entitlements.json"
        ent.write_text(json.dumps({"cluster_write_marker": marker}) + "\n", encoding="utf-8")
        pub = cluster.publish_artifacts("a")
        self.assertTrue(pub["ok"])
        self.assertIn("entitlements.json", pub["published"])
        sync = cluster.sync_from_shared("b")
        self.assertIn("entitlements.json", sync["pulled"])
        copied = json.loads((self.tmp / "b" / "entitlements.json").read_text(encoding="utf-8"))
        self.assertEqual(copied["cluster_write_marker"], marker)

    def test_leader_failover_on_stale(self):
        cluster.bootstrap_pair()
        cluster.record_heartbeat("a")
        cluster.record_heartbeat("b")
        cluster.simulate_stale_node("a")
        status = cluster.cluster_status()
        self.assertEqual(status["leader"], "b")
        with self.assertRaises(ValueError):
            cluster.publish_artifacts("a")
        pub = cluster.publish_artifacts("b")
        self.assertTrue(pub["ok"])

    def test_active_endpoint_uses_leader_port(self):
        cluster.bootstrap_pair()
        cluster.record_heartbeat("b")
        ep = cluster.active_api_endpoint()
        self.assertIn(":8444", ep)


if __name__ == "__main__":
    unittest.main()
