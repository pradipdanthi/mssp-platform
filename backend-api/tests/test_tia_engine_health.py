"""Layered engine health: honest roll-up, caching, timeouts, role gating, and the spoken path.

LOCAL tests. Engine responses are simulated (patched probes); nothing contacts a real engine,
so these prove the decision logic and wiring, not the live state of any VM.
"""

from __future__ import annotations

import time
import unittest
from unittest.mock import patch

import tia_testenv
from test_tia_conversation import TA, ConversationBase, sid


def L(status, reason=None):
    return {"status": status, "reason": reason, "source": "test", "detail": "secret-host-detail", "checked_at": "x"}


class RollUpTests(unittest.TestCase):
    def roll(self, **layers):
        from app.services import tia_engine_health as eh

        full = {k: L("unknown", "no_adapter") for k in eh.LAYERS}
        full.update({k: v for k, v in layers.items()})
        return eh.roll_up(full)

    def test_an_open_port_alone_is_unknown_not_healthy(self) -> None:
        self.assertEqual(self.roll(reachability=L("ok")), ("unknown", "only_port_reachability_verified"))

    def test_unreachable_wins(self) -> None:
        self.assertEqual(self.roll(reachability=L("unreachable", "connection_failed"))[0], "unreachable")

    def test_reachable_but_login_rejected_is_unauthorized_not_ok(self) -> None:
        r = self.roll(reachability=L("ok"), api=L("ok"), auth=L("unauthorized", "credentials_rejected"))
        self.assertEqual(r, ("unauthorized", "credentials_rejected"))

    def test_a_daemon_down_is_degraded_even_when_login_works(self) -> None:
        r = self.roll(reachability=L("ok"), api=L("ok"), auth=L("ok"), application=L("degraded", "core_daemons_not_running"))
        self.assertEqual(r[0], "degraded")

    def test_stale_telemetry_degrades_an_engine_whose_api_is_fine(self) -> None:
        r = self.roll(reachability=L("ok"), api=L("ok"), auth=L("ok"), application=L("ok"), telemetry=L("degraded", "telemetry_stale"))
        self.assertEqual(r, ("degraded", "telemetry_stale"))

    def test_ok_requires_real_evidence_beyond_the_port(self) -> None:
        self.assertEqual(self.roll(reachability=L("ok"), application=L("ok"))[0], "ok")


class AdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        from app.services import tia_engine_health as eh

        eh.clear_cache()

    def spec(self, eid="wazuh"):
        from app.services import tia_engine_health as eh

        return next(s for s in eh._specs() if s["id"] == eid)

    def test_wazuh_reachable_but_credentials_rejected(self) -> None:
        from app.services import tia_engine_health as eh
        from app.services import wazuh_client as w

        with patch.object(eh, "probe_reachability", return_value=L("ok")), patch.object(w, "credentials_configured", return_value=True), patch.object(
            w, "authenticate", side_effect=w.WazuhClientError("HTTP 401", status=401)
        ), patch.object(eh, "probe_telemetry", return_value=L("ok")):
            e = eh.check_engine(self.spec("wazuh"))
        self.assertEqual(e["status"], "unauthorized")
        self.assertEqual(e["layers"]["reachability"]["status"], "ok")
        self.assertEqual(e["layers"]["auth"]["status"], "unauthorized")
        self.assertIn("reachability", e["verified_layers"])

    def test_wazuh_manager_with_a_stopped_daemon_is_degraded_and_names_it(self) -> None:
        from app.services import tia_engine_health as eh
        from app.services import wazuh_client as w

        e = self.wazuh({"wazuh-analysisd": "running", "wazuh-remoted": "stopped", "wazuh-db": "running"})
        self.assertEqual((e["status"], e["reason"]), ("degraded", "core_daemons_not_running"))
        self.assertIn("wazuh-remoted", e["layers"]["application"]["detail"])

    def wazuh(self, daemons, agents=None):
        from app.services import tia_engine_health as eh
        from app.services import wazuh_client as w

        responses = {
            "/": {"data": {"api_version": "4.9.2"}},
            "/security/users/me": {"data": {"affected_items": [{"roles": [{"name": "readonly"}]}]}},
            "/manager/status": {"data": {"affected_items": [daemons]}},
            "/agents/summary/status": {"data": {"connection": agents or {"active": 3, "disconnected": 0, "never_connected": 0}}},
        }
        with patch.object(eh, "probe_reachability", return_value=L("ok")), patch.object(w, "credentials_configured", return_value=True), patch.object(
            w, "authenticate", return_value="tok"
        ), patch.object(w, "_request", side_effect=lambda m, p, **k: responses[p]):
            return eh.check_engine(self.spec("wazuh"))

    def test_optional_wazuh_daemons_that_are_off_by_design_do_not_degrade_the_manager(self) -> None:
        # Observed on the live single-node manager: cluster, mail, csyslog, dbd, agentless, reportd are not running.
        core = {d: "running" for d in ("wazuh-analysisd", "wazuh-remoted", "wazuh-db", "wazuh-modulesd", "wazuh-execd", "wazuh-apid")}
        core.update({d: "stopped" for d in ("wazuh-clusterd", "wazuh-maild", "wazuh-csyslogd", "wazuh-dbd", "wazuh-agentlessd", "wazuh-reportd")})
        e = self.wazuh(core)
        self.assertEqual(e["status"], "ok")
        self.assertIn("optional: wazuh-agentlessd", e["layers"]["application"]["detail"])
        self.assertIn("4.9.2", e["layers"]["api"]["detail"])
        self.assertIn("readonly", e["layers"]["auth"]["detail"])

    def test_wazuh_telemetry_comes_from_agent_keepalives_not_alert_volume(self) -> None:
        core = {"wazuh-analysisd": "running", "wazuh-remoted": "running"}
        e = self.wazuh(core, agents={"active": 2, "disconnected": 1, "never_connected": 0})
        self.assertEqual((e["status"], e["reason"]), ("degraded", "agents_disconnected"))
        e = self.wazuh(core, agents={"active": 0, "disconnected": 0, "never_connected": 0})
        self.assertEqual(e["layers"]["telemetry"]["reason"], "no_agents_enrolled")
        self.assertIn("telemetry", e["unverified_layers"])

    def test_wazuh_without_credentials_does_not_claim_a_healthy_manager(self) -> None:
        from app.services import tia_engine_health as eh
        from app.services import wazuh_client as w

        with patch.object(eh, "probe_reachability", return_value=L("ok")), patch.object(w, "credentials_configured", return_value=False), patch.object(
            eh, "probe_telemetry", return_value=L("unknown", "no_events_recorded")
        ):
            e = eh.check_engine(self.spec("wazuh"))
        self.assertEqual(e["status"], "unknown")
        self.assertEqual(e["layers"]["auth"]["reason"], "credentials_not_configured")

    def test_unreachable_host_does_not_run_authenticated_probes(self) -> None:
        from app.services import tia_engine_health as eh
        from app.services import wazuh_client as w

        with patch.object(eh, "probe_reachability", return_value=L("unreachable", "connection_failed")), patch.object(w, "authenticate") as auth, patch.object(
            eh, "probe_telemetry", return_value=L("ok")
        ):
            e = eh.check_engine(self.spec("wazuh"))
        auth.assert_not_called()
        self.assertEqual(e["status"], "unreachable")
        self.assertEqual(e["layers"]["auth"]["reason"], "host_unreachable")

    def test_engines_without_an_adapter_say_so(self) -> None:
        from app.services import tia_engine_health as eh

        with patch.object(eh, "probe_reachability", return_value=L("ok")), patch.object(eh, "probe_telemetry", return_value=L("unknown", "no_events_recorded")):
            e = eh.check_engine(self.spec("misp"))
        self.assertEqual(e["status"], "unknown")
        self.assertEqual(e["layers"]["auth"]["reason"], "no_adapter")

    def test_a_probe_that_raises_is_reported_unknown_not_ok(self) -> None:
        from app.services import tia_engine_health as eh

        with patch.object(eh, "probe_reachability", return_value=L("ok")), patch.object(eh, "probe_wazuh", side_effect=RuntimeError("boom")), patch.object(
            eh, "probe_telemetry", return_value=L("ok")
        ):
            spec = dict(self.spec("wazuh"))
            spec["probe"] = eh.probe_wazuh
            e = eh.check_engine(spec)
        self.assertNotEqual(e["status"], "ok")

    def test_telemetry_freshness_reads_the_real_database(self) -> None:
        tia_testenv.require_database()
        from app.db.session import execute, fetch_one
        from app.services import tia_engine_health as eh

        tid = "eeeeeeee-9999-0000-0000-00000000000f"
        execute("INSERT INTO tenants (id, name, short_code) VALUES (%s::uuid, 'Health T', 'HLTH') ON CONFLICT DO NOTHING;", (tid,))
        self.addCleanup(execute, "DELETE FROM tenants WHERE id = %s::uuid;", (tid,))
        execute("DELETE FROM security_alerts WHERE source_tool = 'zzhealth';")
        self.assertEqual(eh.probe_telemetry(["zzhealth"], expect_continuous=True, stale_minutes=30)["reason"], "no_events_recorded")
        execute("INSERT INTO security_alerts (tenant_id, source_tool, severity, alert_title, status, created_at) VALUES (%s::uuid,'zzhealth','low','t','new', now() - interval '3 hours');", (tid,))
        stale = eh.probe_telemetry(["zzhealth"], expect_continuous=True, stale_minutes=30)
        self.assertEqual((stale["status"], stale["reason"]), ("degraded", "telemetry_stale"))
        quiet = eh.probe_telemetry(["zzhealth"], expect_continuous=False, stale_minutes=30)
        self.assertEqual(quiet["status"], "unknown")  # a quiet source is not proof of failure
        execute("INSERT INTO security_alerts (tenant_id, source_tool, severity, alert_title, status) VALUES (%s::uuid,'zzhealth','low','t2','new');", (tid,))
        self.assertEqual(eh.probe_telemetry(["zzhealth"], expect_continuous=True, stale_minutes=30)["status"], "ok")
        execute("DELETE FROM security_alerts WHERE source_tool = 'zzhealth';")
        _ = fetch_one


class CacheAndDeadlineTests(unittest.TestCase):
    def setUp(self) -> None:
        from app.services import tia_engine_health as eh

        eh.clear_cache()

    def fake_check(self, spec):
        return {"engine": spec["id"], "label": spec["label"], "host": "10.0.0.9", "port": 1, "vm": "VM", "status": "ok", "reason": None,
                "layers": {k: L("ok") for k in ("reachability", "api", "auth", "application", "telemetry")},
                "verified_layers": [], "unverified_layers": [], "scope": "platform", "checked_at": "t", "duration_ms": 1}

    def test_second_call_is_labelled_cached_with_its_age_and_force_refreshes(self) -> None:
        from app.services import tia_engine_health as eh

        with patch.object(eh, "check_engine", side_effect=self.fake_check) as chk:
            first = eh.get_health(only="wazuh")
            time.sleep(1.1)
            second = eh.get_health(only="wazuh")
            forced = eh.get_health(only="wazuh", force=True)
        self.assertEqual((first["engines"][0]["cached"], first["engines"][0]["freshness"]), (False, "live"))
        self.assertTrue(second["engines"][0]["cached"])
        self.assertGreaterEqual(second["engines"][0]["age_s"], 1)
        self.assertFalse(forced["engines"][0]["cached"])
        self.assertEqual(chk.call_count, 2)

    def test_one_hung_engine_cannot_stall_the_others(self) -> None:
        from app.services import tia_engine_health as eh

        def check(spec):
            if spec["id"] == "thehive":
                time.sleep(3)
            return self.fake_check(spec)

        with patch.dict("os.environ", {"TIA_ENGINE_HEALTH_DEADLINE_SECONDS": "1"}), patch.object(eh, "check_engine", side_effect=check):
            started = time.monotonic()
            report = eh.get_health(force=True)
            elapsed = time.monotonic() - started
        by = {e["engine"]: e for e in report["engines"]}
        self.assertLess(elapsed, 2.5)
        self.assertEqual((by["thehive"]["status"], by["thehive"]["reason"]), ("unknown", "check_timed_out"))
        self.assertEqual(by["wazuh"]["status"], "ok")

    def test_a_timed_out_engine_shows_its_last_result_labelled_cached(self) -> None:
        from app.services import tia_engine_health as eh

        with patch.object(eh, "check_engine", side_effect=self.fake_check):
            eh.get_health(force=True)
        def slow(spec):
            time.sleep(3)
            return self.fake_check(spec)
        with patch.dict("os.environ", {"TIA_ENGINE_HEALTH_DEADLINE_SECONDS": "1"}), patch.object(eh, "check_engine", side_effect=slow):
            report = eh.get_health(force=True, only="wazuh")
        e = report["engines"][0]
        self.assertTrue(e["cached"])
        self.assertIn("timed out", e["note"])

    def test_analysts_get_status_but_not_hosts_or_error_detail(self) -> None:
        from app.services import tia_engine_health as eh

        with patch.object(eh, "check_engine", side_effect=self.fake_check):
            report = eh.get_health(only="wazuh", force=True)
        analyst = eh.redact_for_role(report, "soc_analyst")
        manager = eh.redact_for_role(report, "soc_manager")
        self.assertNotIn("host", analyst["engines"][0])
        self.assertNotIn("detail", analyst["engines"][0]["layers"]["api"])
        self.assertEqual(manager["engines"][0]["host"], "10.0.0.9")

    def test_summary_reports_problems_by_name_and_never_says_all_clear_when_one_is_down(self) -> None:
        from app.services import tia_engine_health as eh

        def check(spec):
            e = self.fake_check(spec)
            if spec["id"] == "wazuh":
                e.update(status="unauthorized", reason="credentials_rejected")
            if spec["id"] == "suricata":
                e.update(status="unknown", reason="only_port_reachability_verified")
            return e

        with patch.object(eh, "check_engine", side_effect=check):
            report = eh.get_health(force=True)
        said = eh.summarize(report)
        self.assertIn("Wazuh Manager is rejecting our login", said["answer"])
        self.assertIn("Suricata", said["answer"])
        self.assertNotIn("All ", said["answer"].split(".")[0])


class SpokenPathTests(ConversationBase):
    def setUp(self) -> None:
        from app.services import tia_engine_health as eh

        eh.clear_cache()

    def degraded(self, spec):
        e = {"engine": spec["id"], "label": spec["label"], "host": "10.0.0.9", "port": 1, "vm": "VM", "status": "ok", "reason": None,
             "layers": {k: L("ok") for k in ("reachability", "api", "auth", "application", "telemetry")},
             "verified_layers": ["reachability"], "unverified_layers": [], "scope": "platform", "checked_at": "t", "duration_ms": 1}
        if spec["id"] == "wazuh":
            e.update(status="unauthorized", reason="credentials_rejected")
        return e

    def test_asking_about_health_runs_the_adapters_and_reports_the_unhealthy_engine(self) -> None:
        from app.services import tia_engine_health as eh

        with patch.object(eh, "check_engine", side_effect=self.degraded):
            out = self.converse("admin", "Are all the engines up and healthy?", sid())
        self.assertEqual((out["tool"], out["tool_ok"]), ("engine_health", True))
        self.assertIn("Wazuh", out["answer"])
        self.assertIn("rejecting our login", out["answer"])

    def test_asking_about_one_engine_focuses_on_it(self) -> None:
        from app.services import tia_engine_health as eh

        with patch.object(eh, "check_engine", side_effect=self.degraded):
            out = self.converse("admin", "Is Wazuh working?", sid())
        self.assertEqual(out["tool"], "engine_health")
        self.assertTrue(out["answer"].startswith("Wazuh Manager is rejecting our login"))

    def test_an_analyst_does_not_receive_infrastructure_addresses(self) -> None:
        from app.services import tia_engine_health as eh

        with patch.object(eh, "check_engine", side_effect=self.degraded):
            r = self.client.get("/admin/soc-console/engine-health?refresh=true", headers=self.users["analyst"]["headers"])
            m = self.client.get("/admin/soc-console/engine-health", headers=self.users["admin"]["headers"])
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("10.0.0.9", r.text)
        self.assertEqual(r.json()["detail_level"], "status_only")
        self.assertIn("10.0.0.9", m.text)

    def test_customers_cannot_reach_engine_health(self) -> None:
        r = self.client.get("/admin/soc-console/engine-health", headers=self.users["customer"]["headers"])
        self.assertIn(r.status_code, (401, 403))
        out = self.client.post("/admin/soc-console/converse", json={"message": "engine health", "session_id": sid()}, headers=self.users["customer"]["headers"])
        self.assertIn(out.status_code, (401, 403))

    def test_alert_counts_questions_do_not_trigger_health(self) -> None:
        out = self.converse("admin", "How many critical alerts are open?", sid(), tenant=None)
        self.assertNotEqual(out["tool"], "engine_health")

    def test_counts_keep_critical_and_high_separate(self) -> None:
        out = self.converse("admin", "How many critical and high alerts are open?", sid(), tenant=TA)
        self.assertRegex(out["answer"], r"2 critical")
        self.assertRegex(out["answer"], r"3 high")
        self.assertNotRegex(out["answer"], r"\b5 critical")


if __name__ == "__main__":
    unittest.main()
