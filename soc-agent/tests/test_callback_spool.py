"""Agent callback: the attempt binding is echoed and an undelivered result is never lost.

LOCAL tests. No network: the HTTP client is replaced. Run:
    cd soc-agent && python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core import callback  # noqa: E402

BINDING = {
    "attempt_id": "11111111-1111-1111-1111-111111111111",
    "job_id": "22222222-2222-2222-2222-222222222222:abc",
    "evidence_version": "abc",
    "tenant_id": "33333333-3333-3333-3333-333333333333",
    "alert_id": "22222222-2222-2222-2222-222222222222",
}


def alert(binding=BINDING) -> dict:
    return {"alert_id": BINDING["alert_id"], "title": "synthetic", "severity": "high", "tenant": "SYNTH", "raw": {"tia": dict(binding)}}


def result() -> dict:
    return {
        "ok": True,
        "alert_id": BINDING["alert_id"],
        "contract": "analyst-result-2",
        "execution": {"status": "succeeded"},
        "llm": {"verdict": "Suspicious", "confidence": 70, "summary": "x", "action_package": {}},
    }


class FakeResponse:
    def __init__(self, status: int) -> None:
        self.status_code = status
        self.content = b"{}"
        self.text = "{}"

    def json(self):
        return {"ok": True, "status": "accepted"}


class FakeClient:
    """Answers with the next status from a script and records every request body."""

    script: list = []
    bodies: list = []

    def __init__(self, *a, **k) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, json=None, headers=None):
        FakeClient.bodies.append(json)
        nxt = FakeClient.script.pop(0) if FakeClient.script else 200
        if isinstance(nxt, Exception):
            raise nxt
        return FakeResponse(nxt)


class SpoolBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(
            os.environ,
            {
                "MSSP_CALLBACK_URL": "http://control-plane.invalid",
                "MSSP_CALLBACK_TOKEN": "synthetic-token",
                "SOC_AGENT_CALLBACK_SPOOL": self.tmp.name,
            },
        )
        env.start()
        self.addCleanup(env.stop)
        client = patch.object(callback.httpx, "Client", FakeClient)
        client.start()
        self.addCleanup(client.stop)
        thread = patch.object(callback, "start_retry_thread")  # the loop is driven by hand
        thread.start()
        self.addCleanup(thread.stop)
        FakeClient.script, FakeClient.bodies = [], []

    def files(self, suffix="*.json"):
        return sorted(Path(self.tmp.name).glob(suffix))


class BindingTests(SpoolBase):
    def test_callback_body_carries_the_attempt_binding(self) -> None:
        body = callback.build_body(result(), alert())
        for key in ("attempt_id", "job_id", "evidence_version", "tenant_id"):
            self.assertEqual(body[key], BINDING[key])

    def test_a_result_without_a_binding_is_still_sent_but_unbound(self) -> None:
        body = callback.build_body(result(), {"alert_id": BINDING["alert_id"], "raw": {}})
        self.assertIsNone(body["attempt_id"])

    def test_the_analyst_echoes_the_binding_on_its_result(self) -> None:
        from app.core import analyst

        res = {"ok": False, "alert_id": BINDING["alert_id"], "execution": {"status": "failed"}}
        with patch.object(analyst, "push_triage_result", return_value={"ok": True}), patch.object(analyst, "audit"):
            out = analyst._finish(res, alert(), "/dev/null")
        self.assertEqual(out["tia_binding"]["attempt_id"], BINDING["attempt_id"])
        self.assertEqual(out["tia_binding"]["evidence_version"], "abc")


class SpoolTests(SpoolBase):
    def test_delivered_first_time_leaves_nothing_in_the_spool(self) -> None:
        FakeClient.script = [200]
        self.assertEqual(callback.push_triage_result(result(), alert())["ok"], True)
        self.assertEqual(self.files(), [])

    def test_control_plane_outage_spools_and_a_later_retry_delivers(self) -> None:
        FakeClient.script = [503, OSError("connection refused"), 200]
        self.assertIsNone(callback.push_triage_result(result(), alert()))
        self.assertEqual(len(self.files()), 1, "an undelivered result is kept")
        now = time.time()
        self.assertEqual(callback.retry_spool_once(now=now)["retry"], 0, "not retried before its backoff elapses")
        self.assertEqual(callback.retry_spool_once(now=now + 3600)["retry"], 1, "still down: kept, backoff grows")
        self.assertEqual(len(self.files()), 1)
        self.assertEqual(callback.retry_spool_once(now=now + 7200)["delivered"], 1)
        self.assertEqual(self.files(), [])
        self.assertTrue(all(b["attempt_id"] == BINDING["attempt_id"] for b in FakeClient.bodies))

    def test_survives_a_restart_because_it_is_on_disk(self) -> None:
        FakeClient.script = [503]
        callback.push_triage_result(result(), alert())
        entry = json.loads(self.files()[0].read_text())
        self.assertEqual(entry["body"]["attempt_id"], BINDING["attempt_id"])
        self.assertEqual(oct(self.files()[0].stat().st_mode & 0o777), "0o600")
        FakeClient.script = [200]
        self.assertEqual(callback.retry_spool_once(now=time.time() + 3600)["delivered"], 1)

    def test_the_same_result_is_spooled_once(self) -> None:
        FakeClient.script = [503, 503]
        callback.push_triage_result(result(), alert())
        callback.push_triage_result(result(), alert())
        self.assertEqual(len(self.files()), 1)

    def test_a_permanent_rejection_is_kept_for_inspection_not_retried(self) -> None:
        FakeClient.script = [503, 409]
        callback.push_triage_result(result(), alert())
        self.assertEqual(callback.retry_spool_once(now=time.time() + 3600)["rejected"], 1)
        self.assertEqual(self.files(), [])
        self.assertEqual(len(self.files("*.rejected")), 1)
        FakeClient.script = [200]
        self.assertEqual(callback.retry_spool_once(now=time.time() + 7200), {"delivered": 0, "retry": 0, "rejected": 0, "expired": 0})

    def test_a_permanent_rejection_on_first_try_is_kept_for_inspection_not_retried(self) -> None:
        FakeClient.script = [404]
        self.assertIsNone(callback.push_triage_result(result(), alert()))
        self.assertEqual(self.files(), [])
        self.assertEqual(len(self.files("*.rejected")), 1)

    def test_an_entry_past_the_retention_limit_is_set_aside_not_deleted(self) -> None:
        FakeClient.script = [503]
        callback.push_triage_result(result(), alert())
        self.assertEqual(callback.retry_spool_once(now=time.time() + 8 * 24 * 3600)["expired"], 1)
        self.assertEqual(len(self.files("*.expired")), 1)

    def test_too_many_requests_is_retried(self) -> None:
        FakeClient.script = [429]
        callback.push_triage_result(result(), alert())
        self.assertEqual(len(self.files()), 1)


if __name__ == "__main__":
    unittest.main()
