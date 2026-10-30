"""Durable investigation jobs: crash recovery, backoff, fairness, dead letters, sweeper.

LOCAL tests against a throwaway Postgres. Process crashes are real: a child Python process
claims a job and is killed with os._exit, leaving only what the database holds.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import unittest
import uuid
from unittest.mock import patch

import tia_testenv

TA = "ffffffff-1111-2222-3333-44444444444a"
TB = "ffffffff-1111-2222-3333-44444444444b"


class JobsBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        tia_testenv.require_database()
        from app.db.session import execute
        from app.services import tia_jobs

        tia_jobs.reset_schema_cache()
        if not tia_jobs.schema_ready():
            raise RuntimeError("migration 120 is not applied to the test database")
        for tid, code in ((TA, "JOBA"), (TB, "JOBB")):
            execute("INSERT INTO tenants (id, name, short_code) VALUES (%s::uuid, %s, %s) ON CONFLICT DO NOTHING;", (tid, f"Jobs {code}", code))

    @classmethod
    def tearDownClass(cls) -> None:
        from app.db.session import execute

        for tid in (TA, TB):
            execute("DELETE FROM tenants WHERE id = %s::uuid;", (tid,))

    def setUp(self) -> None:
        from app.db.session import execute

        execute("DELETE FROM tia_jobs;")  # throwaway database: no job from another test may leak in
        execute("DELETE FROM security_alerts WHERE tenant_id IN (%s::uuid, %s::uuid);", (TA, TB))
        from app.services import tia_jobs

        tia_jobs.COUNTERS.update({k: 0 for k in tia_jobs.COUNTERS})

    def alert(self, severity="critical", tenant=TA, status="new", age="0 seconds"):
        from app.db.session import fetch_one

        return fetch_one(
            "INSERT INTO security_alerts (tenant_id, source_tool, severity, alert_title, status, created_at) "
            "VALUES (%s::uuid, 'wazuh', %s, %s, %s, now() - %s::interval) RETURNING id::text AS id;",
            (tenant, severity, f"job test {uuid.uuid4().hex[:6]}", status, age),
        )["id"]

    def job(self, alert_id):
        from app.db.session import fetch_one

        return fetch_one("SELECT state, attempts, dead_reason, last_error_category, lease_owner, source FROM tia_jobs WHERE alert_id = %s::uuid ORDER BY created_at DESC LIMIT 1;", (alert_id,)) or None

    def expire_lease(self, alert_id):
        from app.db.session import execute

        execute("UPDATE tia_jobs SET lease_expires_at = now() - interval '1 second' WHERE alert_id = %s::uuid AND state = 'running';", (alert_id,))

    def make_ready(self, alert_id):
        from app.db.session import execute

        execute("UPDATE tia_jobs SET next_run_at = now() - interval '1 second' WHERE alert_id = %s::uuid;", (alert_id,))


class QueueSemanticsTests(JobsBase):
    def test_enqueue_is_idempotent_per_alert(self) -> None:
        from app.services import tia_jobs

        a = self.alert()
        first = tia_jobs.enqueue(alert_id=a, tenant_id=TA, severity="critical")
        second = tia_jobs.enqueue(alert_id=a, tenant_id=TA, severity="critical")
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(first["job_id"], second["job_id"])

    def test_priority_order_is_critical_then_high_then_other(self) -> None:
        from app.services import tia_jobs

        low, high, crit = self.alert("medium"), self.alert("high"), self.alert("critical")
        for a, sev in ((low, "medium"), (high, "high"), (crit, "critical")):
            tia_jobs.enqueue(alert_id=a, tenant_id=TA, severity=sev)
        with patch.dict(os.environ, {"TIA_TENANT_MAX_RUNNING": "10"}):
            order = [tia_jobs.claim("w")["alert_id"] for _ in range(3)]
        self.assertEqual(order, [crit, high, low])

    def test_a_tenant_cannot_occupy_every_worker(self) -> None:
        from app.services import tia_jobs

        a_alerts = [self.alert("critical", TA) for _ in range(3)]
        b_alert = self.alert("high", TB)
        for a in a_alerts:
            tia_jobs.enqueue(alert_id=a, tenant_id=TA, severity="critical")
        tia_jobs.enqueue(alert_id=b_alert, tenant_id=TB, severity="high")
        with patch.dict(os.environ, {"TIA_TENANT_MAX_RUNNING": "2"}):
            claimed = [tia_jobs.claim("w")["alert_id"] for _ in range(3)]
        self.assertEqual(claimed[2], b_alert, "the third claim goes to the other tenant, not a third job of the same one")

    def test_a_failing_job_backs_off_without_blocking_other_jobs(self) -> None:
        from app.services import tia_jobs

        bad, good = self.alert("critical"), self.alert("high")
        tia_jobs.enqueue(alert_id=bad, tenant_id=TA, severity="critical")
        tia_jobs.enqueue(alert_id=good, tenant_id=TA, severity="high")
        job = tia_jobs.claim("w")
        self.assertEqual(job["alert_id"], bad)
        res = tia_jobs.fail(job["id"], "timeout", "w")
        self.assertEqual(res["state"], "queued")
        started = time.monotonic()
        nxt = tia_jobs.claim("w")
        self.assertEqual(nxt["alert_id"], good)  # picked immediately: nothing slept
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertIsNone(tia_jobs.claim("w"))  # the failed job is waiting for its backoff, not spinning

    def test_attempts_are_bounded_then_the_job_dead_letters_with_a_review(self) -> None:
        from app.services import tia_jobs

        a = self.alert()
        tia_jobs.enqueue(alert_id=a, tenant_id=TA, severity="critical")
        reviews = []
        with patch.object(tia_jobs, "_record_dead_review", side_effect=reviews.append):
            outcomes = []
            for _ in range(10):
                self.make_ready(a)
                res = tia_jobs.run_one(lambda al, t: (False, "timeout"), "w")
                if res is None:
                    break
                outcomes.append(res["outcome"])
                if res["outcome"] == "dead":
                    break
        self.assertEqual(outcomes, ["queued", "queued", "queued", "dead"])
        self.assertEqual(self.job(a)["dead_reason"], "timeout")
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0]["alert_id"], a)

    def test_infrastructure_outage_defers_without_spending_attempts(self) -> None:
        from app.services import tia_jobs

        a = self.alert()
        tia_jobs.enqueue(alert_id=a, tenant_id=TA, severity="critical")
        for _ in range(8):
            self.make_ready(a)
            tia_jobs.run_one(lambda al, t: (False, "schema_not_ready"), "w")
        row = self.job(a)
        self.assertEqual((row["state"], row["attempts"]), ("queued", 0))

    def test_an_unavailable_database_during_the_handler_defers_too(self) -> None:
        import psycopg

        from app.services import tia_jobs

        a = self.alert()
        tia_jobs.enqueue(alert_id=a, tenant_id=TA, severity="critical")

        def boom(al, t):
            raise psycopg.OperationalError("db gone")

        tia_jobs.run_one(boom, "w")
        row = self.job(a)
        self.assertEqual((row["state"], row["attempts"], row["last_error_category"]), ("queued", 0, "database_error"))


class CrashRecoveryTests(JobsBase):
    CHILD = (
        "import os,sys;sys.path.insert(0,'/app');"
        "from app.services import tia_jobs;"
        "j=tia_jobs.claim('crashing-worker');"
        "print(j['alert_id'] if j else 'NONE', flush=True);"
        "os._exit(137)"
    )

    def crash_after_claim(self, alert_id):
        out = subprocess.run([sys.executable, "-c", self.CHILD], capture_output=True, text=True, timeout=60, env=dict(os.environ))
        self.assertEqual(out.stdout.strip(), alert_id, out.stderr[-400:])
        self.assertEqual(out.returncode, 137)

    def test_a_worker_process_killed_mid_analysis_loses_nothing(self) -> None:
        from app.services import tia_jobs

        a = self.alert()
        tia_jobs.enqueue(alert_id=a, tenant_id=TA, severity="critical")
        self.crash_after_claim(a)
        self.assertEqual(self.job(a)["state"], "running")  # the row survived the crash
        self.assertEqual(self.job(a)["lease_owner"], "crashing-worker")
        self.assertIsNone(tia_jobs.claim("other"))  # lease still valid: nobody steals live work
        self.expire_lease(a)
        stats = tia_jobs.stats()
        self.assertGreaterEqual(stats["expired_leases"], 1)  # observable before recovery
        recovered = tia_jobs.recover_expired()
        self.assertEqual([r["alert_id"] for r in recovered], [a])
        again = tia_jobs.claim("other")
        self.assertEqual((again["alert_id"], again["attempts"]), (a, 2))  # the crashed attempt was counted
        self.assertTrue(tia_jobs.complete(again["id"], "other"))
        self.assertEqual(self.job(a)["state"], "succeeded")

    def test_repeated_crashes_end_in_a_dead_job_not_an_endless_loop(self) -> None:
        from app.services import tia_jobs

        a = self.alert()
        tia_jobs.enqueue(alert_id=a, tenant_id=TA, severity="critical")
        final = None
        for _ in range(tia_jobs.max_attempts() + 1):
            self.make_ready(a)
            j = tia_jobs.claim("w")
            if not j:
                break
            self.expire_lease(a)
            rows = tia_jobs.recover_expired()
            final = rows[0]["state"] if rows else final
        self.assertEqual(final, "dead")
        self.assertEqual(self.job(a)["dead_reason"], "lease_expired")

    def test_a_worker_that_lost_its_lease_cannot_complete_or_fail_the_new_owners_job(self) -> None:
        from app.services import tia_jobs

        a = self.alert()
        tia_jobs.enqueue(alert_id=a, tenant_id=TA, severity="critical")
        old = tia_jobs.claim("old")
        self.expire_lease(a)
        tia_jobs.recover_expired()
        new = tia_jobs.claim("new")
        self.assertFalse(tia_jobs.complete(old["id"], "old"))
        self.assertEqual(tia_jobs.fail(old["id"], "timeout", "old")["state"], "lost")
        self.assertEqual(self.job(a)["lease_owner"], "new")
        self.assertTrue(tia_jobs.complete(new["id"], "new"))
        self.assertEqual(tia_jobs.COUNTERS["lease_lost"], 2)

    def test_work_that_finished_but_was_never_acknowledged_is_delivered_again(self) -> None:
        """Crash AFTER the effect committed and BEFORE complete(): the job is delivered a second time.

        This is the at-least-once guarantee, stated honestly. Safety on the second delivery comes from the
        effect itself being idempotent (tia_acceptance keeps one immutable result per attempt; ticket and
        notification writes are keyed) - covered by test_tia_acceptance, not by the queue.
        """
        from app.services import tia_jobs

        a = self.alert()
        tia_jobs.enqueue(alert_id=a, tenant_id=TA, severity="critical")
        runs = []

        def effect(alert_id, tenant_id):
            runs.append(alert_id)
            return True, None

        job = tia_jobs.claim("w1")
        effect(job["alert_id"], job["tenant_id"])  # effect done, then the worker "dies" before complete()
        self.assertEqual(self.job(a)["state"], "running")
        self.expire_lease(a)
        tia_jobs.recover_expired()
        res = tia_jobs.run_one(effect, "w2")
        self.assertEqual(res["outcome"], "succeeded")
        self.assertEqual(runs, [a, a])
        self.assertEqual(self.job(a)["state"], "succeeded")

    def test_graceful_shutdown_hands_leased_work_back_without_spending_the_attempt(self) -> None:
        from app.services import tia_jobs

        a = self.alert()
        tia_jobs.enqueue(alert_id=a, tenant_id=TA, severity="critical")
        job = tia_jobs.claim(f"{tia_jobs.WORKER_ID}#0")
        self.assertEqual(job["attempts"], 1)
        tia_jobs.shutdown(timeout=0.2)
        row = self.job(a)
        self.assertEqual((row["state"], row["attempts"], row["last_error_category"]), ("queued", 0, "released_on_shutdown"))


class WorkerAndIngestTests(JobsBase):
    def test_workers_process_jobs_end_to_end_and_stop_cleanly(self) -> None:
        from app.services import tia_jobs

        alerts = [self.alert("critical") for _ in range(3)]
        for a in alerts:
            tia_jobs.enqueue(alert_id=a, tenant_id=TA, severity="critical")
        seen = []
        lock = threading.Lock()

        def handler(alert_id, tenant_id):
            with lock:
                seen.append(alert_id)
            return True, None

        with patch.dict(os.environ, {"TIA_WORKERS": "2", "TIA_TENANT_MAX_RUNNING": "2"}):
            self.assertEqual(tia_jobs.start_workers(handler), 2)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and any(self.job(a)["state"] != "succeeded" for a in alerts):
                time.sleep(0.2)
            tia_jobs.shutdown(timeout=10)
        self.assertEqual(sorted(seen), sorted(alerts))
        self.assertEqual({self.job(a)["state"] for a in alerts}, {"succeeded"})
        self.assertEqual(tia_jobs.alive_workers(), 0)

    def test_sweeper_picks_up_alerts_with_no_record_and_only_those(self) -> None:
        from app.db.session import execute
        from app.services import tia_jobs

        missing = self.alert("critical", age="10 minutes")
        fresh = self.alert("critical", age="10 seconds")  # normal enqueue is still in flight
        closed = self.alert("critical", status="closed", age="10 minutes")
        medium = self.alert("medium", age="10 minutes")
        has_job = self.alert("high", age="10 minutes")
        tia_jobs.enqueue(alert_id=has_job, tenant_id=TA, severity="high")
        with patch.dict(os.environ, {"AI_ALERT_MIN_SEVERITY": "high", "TIA_SWEEP_MISSING": "true"}):
            tia_jobs.sweep_missing()
        self.assertEqual(self.job(missing)["source"], "sweeper")
        for untouched in (fresh, closed, medium):
            self.assertIsNone(self.job(untouched))
        self.assertEqual(self.job(has_job)["source"], "ingest")
        execute("DELETE FROM tia_jobs WHERE alert_id = %s::uuid;", (missing,))

    def test_legacy_redis_items_are_moved_without_loss(self) -> None:
        from app.services import ai_alert_queue as q
        from app.services import tia_jobs

        class FakeRedis:
            def __init__(self, items):
                self.items = list(items)

            def lrange(self, key, a, b):
                return list(self.items)[a : b + 1]

            def lrem(self, key, n, v):
                self.items.remove(v)
                return 1

        a = self.alert()
        good = json.dumps({"alert_id": a, "tenant_id": TA})
        gone = json.dumps({"alert_id": str(uuid.uuid4()), "tenant_id": TA})  # alert deleted since
        junk = "not json"
        fake = FakeRedis([good, gone, junk])
        with patch.object(q, "_redis", return_value=fake):
            moved = tia_jobs.drain_legacy_redis()
        self.assertEqual(fake.items, [])
        self.assertEqual(moved, 1)  # only the valid, existing alert becomes a job
        self.assertEqual(self.job(a)["source"], "legacy_redis")

    def test_enqueue_never_runs_the_pipeline_inline(self) -> None:
        from app.services import ai_alert_queue as q
        from app.services import tia_jobs

        a = self.alert()
        with patch.object(q, "_ai_pipeline_enabled", return_value=True), patch.object(q, "severity_meets_threshold", return_value=True), patch.object(
            q, "_run_ai_pipeline"
        ) as inline, patch.object(q, "_ensure_worker"):
            self.assertTrue(q.enqueue_ai_alert_analysis(alert_id=a, tenant_id=TA, severity="critical"))
            self.assertEqual(self.job(a)["state"], "queued")
            with patch.object(tia_jobs, "enqueue", side_effect=RuntimeError("db down")):
                self.assertFalse(q.enqueue_ai_alert_analysis(alert_id=a, tenant_id=TA, severity="critical"))  # reported, not faked
            with patch.object(tia_jobs, "schema_ready", return_value=False), patch.object(q, "_redis", return_value=None):
                self.assertFalse(q.enqueue_ai_alert_analysis(alert_id=a, tenant_id=TA, severity="critical"))
        inline.assert_not_called()

    def test_job_handler_reports_the_failure_category(self) -> None:
        from app.services import ai_alert_queue as q
        from app.services.tia_schema import SchemaNotReady

        with patch.object(q, "ai_alert_enabled", return_value=False), patch.object(q, "ai_soc_triage_enabled", return_value=False), patch.object(
            q, "deep_triage_enabled", return_value=True
        ), patch.object(q, "process_deep_triage_job", side_effect=SchemaNotReady(["x"])):
            self.assertEqual(q.job_handler("a", "t"), (False, "schema_not_ready"))
        with patch.object(q, "ai_alert_enabled", return_value=False), patch.object(q, "ai_soc_triage_enabled", return_value=False), patch.object(
            q, "deep_triage_enabled", return_value=True
        ), patch.object(q, "process_deep_triage_job", return_value=True):
            self.assertEqual(q.job_handler("a", "t"), (True, None))

    def test_job_handler_investigates_when_only_the_soc_agent_is_on(self) -> None:
        from app.services import ai_alert_queue as q

        with patch.object(q, "ai_alert_enabled", return_value=False), patch.object(
            q, "ai_soc_triage_enabled", return_value=False
        ), patch.object(q, "deep_triage_enabled", return_value=False), patch.object(
            q, "soc_agent_enabled", return_value=True
        ), patch.object(q, "process_deep_triage_job", return_value=True) as deep:
            self.assertEqual(q.job_handler("a", "t"), (True, None))
            deep.assert_called_once_with(alert_id="a", tenant_id="t")
        with patch.object(q, "ai_alert_enabled", return_value=False), patch.object(
            q, "ai_soc_triage_enabled", return_value=False
        ), patch.object(q, "deep_triage_enabled", return_value=False), patch.object(
            q, "soc_agent_enabled", return_value=False
        ), patch.object(q, "process_deep_triage_job", return_value=True) as deep:
            self.assertEqual(q.job_handler("a", "t"), (False, "job_failed"))
            deep.assert_not_called()

    def test_readiness_surfaces_stalled_critical_work_and_missing_workers(self) -> None:
        from app.services import ai_alert_queue as q
        from app.services import tia_jobs, tia_schema

        a = self.alert()
        tia_jobs.enqueue(alert_id=a, tenant_id=TA, severity="critical")
        self.make_ready(a)
        from app.db.session import execute

        execute("UPDATE tia_jobs SET next_run_at = now() - interval '20 minutes' WHERE alert_id = %s::uuid;", (a,))
        tia_schema.reset_cache()
        with patch.object(q, "_ai_pipeline_enabled", return_value=True):
            r = tia_schema.readiness()
        codes = {f["code"]: f["severity"] for f in r["faults"]}
        self.assertEqual(codes.get("critical_queue_stalled"), "fault")
        self.assertEqual(codes.get("job_workers_not_running"), "fault")
        self.assertGreaterEqual(r["backlog"]["jobs"]["queued_critical"], 1)

    def test_manual_review_drains_a_non_empty_queue_and_still_accepts_incoming(self) -> None:
        from app.services import tia_investigation as tia
        from app.services import tia_jobs

        queued = [self.alert("critical") for _ in range(3)]
        for a in queued:
            tia_jobs.enqueue(alert_id=a, tenant_id=TA, severity="critical")
        seen = []

        def handler(alert_id, tenant_id):
            if tia.investigation_mode() != "manual_review":
                raise AssertionError("model path must not run during drain")
            seen.append(alert_id)
            return True, "manual_review_mode"

        with patch.dict(os.environ, {"TIA_INVESTIGATION_MODE": "manual_review"}):
            drained = 0
            while tia_jobs.run_one(handler, "drain-w"):
                drained += 1
            incoming = self.alert("high")
            tia_jobs.enqueue(alert_id=incoming, tenant_id=TA, severity="high", source="operator")
            while tia_jobs.run_one(handler, "drain-w"):
                drained += 1
        self.assertEqual(drained, 4)
        self.assertEqual(tia_jobs.stats()["queued"], 0)
        self.assertEqual(set(seen), set(queued + [incoming]))
        for a in queued + [incoming]:
            self.assertEqual(self.job(a)["state"], "succeeded")


if __name__ == "__main__":
    unittest.main()
