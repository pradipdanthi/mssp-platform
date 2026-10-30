"""Evidence dossier, tenant-scoped research, ticket notes, and cross-attempt effect identity.

LOCAL tests against a throwaway Postgres with SYNTHETIC alerts. No external site is contacted:
research uses an injected fetcher. They prove mechanics, not investigation quality.
"""

from __future__ import annotations

import threading
import unittest
import uuid
from unittest.mock import patch

import tia_testenv

TA = "dddddddd-1111-2222-3333-44444444444a"
TB = "dddddddd-1111-2222-3333-44444444444b"


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        tia_testenv.require_database()
        from app.db.session import execute, fetch_one

        if not fetch_one("SELECT to_regclass('public.tia_effects') AS t;").get("t"):
            raise RuntimeError("migration 122 is not applied to the test database")
        for tid, code in ((TA, "EVDA"), (TB, "EVDB")):
            execute("INSERT INTO tenants (id, name, short_code) VALUES (%s::uuid, %s, %s) ON CONFLICT DO NOTHING;", (tid, f"Evidence {code}", code))

    @classmethod
    def tearDownClass(cls) -> None:
        from app.db.session import execute

        for tid in (TA, TB):
            execute("DELETE FROM tenants WHERE id = %s::uuid;", (tid,))

    def setUp(self) -> None:
        from app.db.session import execute

        for t in ("tia_effects", "tia_research_disclosures", "tia_research_grants", "tia_notifications", "tia_review_items"):
            execute(f"DELETE FROM {t} WHERE tenant_id IN (%s::uuid, %s::uuid);", (TA, TB))
        execute("DELETE FROM tia_jobs WHERE tenant_id IN (%s::uuid, %s::uuid);", (TA, TB))
        execute("DELETE FROM incidents WHERE tenant_id IN (%s::uuid, %s::uuid);", (TA, TB))
        execute("DELETE FROM security_alerts WHERE tenant_id IN (%s::uuid, %s::uuid);", (TA, TB))
        execute("DELETE FROM protected_assets WHERE tenant_id IN (%s::uuid, %s::uuid);", (TA, TB))
        execute("DELETE FROM tia_runbooks WHERE detection_key LIKE 'wazuh:rule:9999%%';")

    def alert(self, tenant=TA, title="Synthetic: winword.exe spawned encoded powershell.exe", severity="high", host="HOST-SYN-1", user="SYN\\alice", src="10.9.9.9", rule="99991", parent="C:\\Program Files\\Microsoft Office\\winword.exe", cmd="powershell.exe -nop -enc SQBFAFgA", minutes_ago=0):
        from app.db.session import fetch_one

        return fetch_one(
            "INSERT INTO security_alerts (tenant_id, source_tool, severity, alert_title, alert_description, source_ip, destination_host, source_user, "
            "parent_process, parent_command_line, raw_event, status, event_time) VALUES (%s::uuid, 'wazuh', %s, %s, 'Office application spawned a shell', %s::inet, %s, %s, %s, %s, "
            "jsonb_build_object('rule', jsonb_build_object('id', %s::text, 'description', 'Office spawned PowerShell')), 'new', now() - make_interval(mins => %s)) RETURNING id::text AS id;",
            (tenant, severity, title, src, host, user, parent, cmd, rule, minutes_ago),
        )["id"]

    def incident(self, alert_id, tenant=TA, status="open"):
        from app.db.session import fetch_one

        return fetch_one(
            "INSERT INTO incidents (tenant_id, primary_alert_id, incident_number, title, severity, status) "
            "VALUES (%s::uuid, %s::uuid, %s, 'Synthetic incident', 'high', %s) RETURNING id::text AS id;",
            (tenant, alert_id, f"INC-SYN-{uuid.uuid4().hex[:6]}", status),
        )["id"]

    def grant(self, provider, query_class, tenant=TA, valid_to="now() + interval '30 days'"):
        from app.db.session import execute

        execute(
            f"INSERT INTO tia_research_grants (tenant_id, provider, query_class, approved_by, customer_reference, valid_to) "
            f"VALUES (%s::uuid, %s, %s, 'ciso@customer.example', 'DPA-2026-07', {valid_to});",
            (tenant, provider, query_class),
        )


class DossierTests(Base):
    def test_sections_carry_source_freshness_and_gaps(self) -> None:
        from app.services import tia_evidence as ev

        a = self.alert()
        self.alert(title="Synthetic: suspicious outbound from same host", severity="medium", minutes_ago=30)
        self.alert(tenant=TB)  # same host name in another tenant must not correlate
        d = ev.build(TA, a)
        s = d["sections"]
        self.assertEqual(set(s), set(ev.SECTIONS))
        self.assertEqual(s["raw_event"]["status"], "present")
        self.assertIn("parent command line", s["raw_event"]["items"]["fields"])
        self.assertEqual(s["correlations"]["status"], "present")
        self.assertEqual(len(s["correlations"]["items"]["related"]), 1)
        self.assertIn("same host", s["correlations"]["items"]["related"][0]["matched_on"])
        self.assertEqual(s["asset"]["status"], "empty")  # not in the inventory: said, not hidden
        self.assertEqual(s["runbooks"]["status"], "empty")
        self.assertEqual(s["prior_cases"]["status"], "empty")
        self.assertTrue(all("read_at" in x and "source" in x for x in s.values()))
        self.assertEqual(ev.build(TB, a), None)  # another tenant cannot build this alert's dossier

    def test_a_failing_source_is_unavailable_not_empty(self) -> None:
        from app.services import tia_evidence as ev

        a = self.alert()
        with patch.dict(ev._BUILDERS, {"correlations": lambda _a: (_ for _ in ()).throw(RuntimeError("db down"))}):
            d = ev.build(TA, a)
        self.assertEqual(d["sections"]["correlations"]["status"], "unavailable")
        self.assertIn("nothing can be concluded", d["sections"]["correlations"]["note"])

    def test_approved_runbooks_and_human_reviewed_precedent_are_retrieved(self) -> None:
        from app.db.session import execute
        from app.services import tia_evidence as ev

        execute("INSERT INTO tia_runbooks (detection_key, title, body, version, status) VALUES ('wazuh:rule:99991', 'Draft', 'draft text', 1, 'draft');")
        execute(
            "INSERT INTO tia_runbooks (detection_key, title, body, version, status, approved_by, approved_at) "
            "VALUES ('wazuh:rule:99991', 'Office spawning PowerShell', 'Check the document origin and the decoded command.', 2, 'approved', 'soc.lead@mssp.example', now());"
        )
        old = self.alert(minutes_ago=60 * 24 * 3)
        execute("UPDATE security_alerts SET status = 'false_positive' WHERE id = %s::uuid;", (old,))
        execute(
            "INSERT INTO tia_review_items (tenant_id, alert_id, reason_code, execution_status, assessed_priority, notify_urgency, due_at, status, resolved_at, resolved_by) "
            "VALUES (%s::uuid, %s::uuid, 'policy_required', 'succeeded', 'P3', 'queue', now(), 'resolved', now(), 'soc.analyst@mssp.example');",
            (TA, old),
        )
        d = ev.build(TA, self.alert())
        books = d["sections"]["runbooks"]["items"]["runbooks"]
        self.assertEqual([b["version"] for b in books], [2])  # drafts are never investigation context
        self.assertEqual(d["sections"]["prior_cases"]["status"], "present")
        self.assertEqual(d["sections"]["prior_cases"]["items"][0]["resolved_by"], "soc.analyst@mssp.example")
        execute("DELETE FROM tia_runbooks WHERE detection_key = 'wazuh:rule:99991';")

    def test_redacted_form_withholds_raw_events_names_and_addresses(self) -> None:
        from app.services import tia_evidence as ev

        a = self.alert()
        red = ev.redacted(ev.build(TA, a))
        text = str(red)
        for secret in ("HOST-SYN-1", "alice", "10.9.9.9", "SQBFAFgA", "winword.exe"):
            self.assertNotIn(secret, text)
        self.assertEqual(red["detail_level"], "redacted")

    def test_full_context_needs_the_tenants_grant_for_that_model_provider(self) -> None:
        from app.services import tia_evidence as ev

        a = self.alert()
        self.assertEqual(ev.for_agent(TA, a)["manifest"]["sent_form"], "redacted")
        self.grant("cursor", "investigation_context", tenant=TB)  # another customer's consent does not count
        self.assertEqual(ev.for_agent(TA, a)["manifest"]["sent_form"], "redacted")
        self.grant("cursor", "investigation_context")
        out = ev.for_agent(TA, a)
        self.assertEqual(out["manifest"]["sent_form"], "full")
        self.assertIn("HOST-SYN-1", str(out["payload"]))

    def test_the_manifest_is_recorded_on_the_attempt_and_the_payload_reaches_the_agent(self) -> None:
        from app.db.session import fetch_one
        from app.services import ai_deep_triage as dt
        from app.services import soc_agent_client as sac
        from app.services import tia_acceptance as acc

        a = self.alert()
        b = acc.open_attempt(alert_id=a, tenant_id=TA)
        enriched = dt._with_evidence({"id": a, "title": "t"}, alert_id=a, tenant_id=TA, attempt_id=b["attempt_id"])
        payload = sac.build_agent_payload(enriched, b)
        self.assertEqual(payload["raw"]["tia_evidence"]["detail_level"], "redacted")
        self.assertEqual(payload["raw"]["research_policy"]["ip_reputation"], [])
        row = fetch_one("SELECT evidence_manifest FROM tia_investigation_attempts WHERE id = %s::uuid;", (b["attempt_id"],))
        self.assertEqual(row["evidence_manifest"]["sent_form"], "redacted")
        self.assertIn("correlations", row["evidence_manifest"]["sections"])


class ResearchPolicyTests(Base):
    def page(self, url):
        return {"ok": True, "status": 200, "source_url": url, "fetched_at": "2026-10-30T00:00:00+00:00", "trust": "untrusted_external_content",
                "excerpt": "PowerShell ... -EncodedCommand ... -nop ... T1059.001 T1027 documented abuse"}

    def test_no_grant_refuses_and_records_the_refusal(self) -> None:
        from app.db.session import fetch_all
        from app.services import tia_evidence as ev
        from app.services import tia_research_policy as rp

        a = ev.load_alert(TA, self.alert())
        with patch.dict("os.environ", {"TIA_RESEARCH_ALLOWED_DOMAINS": "lolbas-project.github.io"}):
            with self.assertRaises(rp.Refused) as cm:
                rp.behavioural_lookup(tenant_id=TA, alert=a, provider="lolbas", requested_by="test", fetcher=self.page)
        self.assertEqual(cm.exception.code, "tenant_not_authorised")
        rows = fetch_all("SELECT outcome, refusal_reason, query_text FROM tia_research_disclosures WHERE tenant_id = %s::uuid;", (TA,))
        self.assertEqual([(r["outcome"], r["refusal_reason"]) for r in rows], [("refused", "tenant_not_authorised")])

    def test_global_allow_list_is_also_required(self) -> None:
        from app.services import tia_evidence as ev
        from app.services import tia_research_policy as rp

        self.grant("lolbas", "behavioural_query")
        a = ev.load_alert(TA, self.alert())
        with patch.dict("os.environ", {"TIA_RESEARCH_ALLOWED_DOMAINS": ""}):
            with self.assertRaises(rp.Refused) as cm:
                rp.behavioural_lookup(tenant_id=TA, alert=a, provider="lolbas", requested_by="test", fetcher=self.page)
        self.assertEqual(cm.exception.code, "host_not_allowed")

    def test_only_public_binary_names_leave_and_the_application_is_computed_locally(self) -> None:
        from app.db.session import fetch_all
        from app.services import tia_evidence as ev
        from app.services import tia_research_policy as rp

        self.grant("lolbas", "behavioural_query")
        aid = self.alert(cmd="powershell.exe -nop -enc SQBFAFgA acme_payroll_sync.exe \\\\fileserver01\\share")
        a = ev.load_alert(TA, aid)
        sent_urls = []
        with patch.dict("os.environ", {"TIA_RESEARCH_ALLOWED_DOMAINS": "lolbas-project.github.io"}):
            out = rp.behavioural_lookup(tenant_id=TA, alert=a, provider="lolbas", requested_by="test", fetcher=lambda u: (sent_urls.append(u), self.page(u))[1])
        self.assertEqual(out["sent"], ["winword.exe", "powershell.exe"])
        self.assertGreaterEqual(out["withheld_names"], 1)
        for u in sent_urls:
            for leak in ("acme", "fileserver01", "SQBFAFgA", "alice", "HOST-SYN-1", "-nop"):
                self.assertNotIn(leak, u)
        ps = [f for f in out["findings"] if f["binary"] == "powershell.exe"][0]
        self.assertIn("-nop", ps["alert_flags_documented_as_abuse"])
        self.assertIn("T1059.001", ps["documented_techniques"])
        rows = fetch_all("SELECT query_text, outcome, source_url FROM tia_research_disclosures WHERE alert_id = %s::uuid ORDER BY created_at;", (aid,))
        self.assertEqual({r["query_text"] for r in rows}, {"winword.exe", "powershell.exe"})
        self.assertTrue(all(r["source_url"] for r in rows))
        d = ev.build(TA, aid)
        self.assertEqual(d["sections"]["research"]["status"], "present")
        by_name = {i["query_text"]: i for i in d["sections"]["research"]["items"]}
        self.assertEqual(set(by_name), {"winword.exe", "powershell.exe"})
        for item in by_name.values():
            self.assertIn(item["result"], ("documented by the provider", "provider has no entry for this name; absence is not evidence of safety"))

    def test_expired_or_revoked_grants_do_not_count(self) -> None:
        from app.db.session import execute
        from app.services import tia_research_policy as rp

        self.grant("lolbas", "behavioural_query", valid_to="now() + interval '1 second'")
        execute("UPDATE tia_research_grants SET valid_from = now() - interval '2 days', valid_to = now() - interval '1 day' WHERE tenant_id = %s::uuid;", (TA,))
        self.assertFalse(rp.granted(TA, "lolbas", "behavioural_query"))
        execute("UPDATE tia_research_grants SET revoked_at = now() WHERE tenant_id = %s::uuid;", (TA,))  # renewal = revoke + new grant
        self.grant("lolbas", "behavioural_query")
        execute("UPDATE tia_research_grants SET revoked_at = now() WHERE tenant_id = %s::uuid AND valid_to > now();", (TA,))
        self.assertFalse(rp.granted(TA, "lolbas", "behavioural_query"))
        self.assertTrue(rp.granted(None, "nvd", "public_identifier"))
        self.assertFalse(rp.granted(None, "lolbas", "behavioural_query"))

    def test_hash_lookup_tool_needs_the_tenants_grant(self) -> None:
        from app.services import tia_tools as tools

        scope = tools.Scope(operator_email="m@x", operator_id=None, role="soc_manager", session_id="s", tenant_id=TA)
        with patch.dict("os.environ", {"TIA_RESEARCH_ALLOWED_DOMAINS": "virustotal.com"}):
            with self.assertRaises(tools.ToolError) as cm:
                tools.research_lookup(scope, kind="sha256", value="a" * 64)
        self.assertEqual(cm.exception.code, "tenant_not_authorised")

    def test_agent_policy_lists_only_granted_ip_providers(self) -> None:
        from app.services import tia_research_policy as rp

        self.assertEqual(rp.agent_research_policy(TA)["ip_reputation"], [])
        self.grant("otx", "ip_reputation")
        self.assertEqual(rp.agent_research_policy(TA)["ip_reputation"], ["otx"])
        self.assertEqual(rp.agent_research_policy(TB)["ip_reputation"], [])


class TicketNoteTests(Base):
    def investigated(self, alert_id, verdict="suspicious"):
        from app.services import tia_acceptance as acc

        b = acc.open_attempt(alert_id=alert_id, tenant_id=TA)
        raw = {
            "ok": True, "contract": "analyst-result-2", "alert_id": alert_id,
            "execution": {"status": "succeeded", "provider": "cursor-agent", "model_selector": "account_default", "cli_version": "9.9.9", "prompt_version": "soc-analyst-1"},
            "llm": {"verdict": verdict.capitalize(), "confidence": 70, "summary": "Office macro launched an encoded PowerShell command.", "root_cause": "Possible phishing document.", "escalate_to_human": False},
            "tia_binding": {k: b[k] for k in ("attempt_id", "job_id", "evidence_version", "tenant_id", "alert_id")},
        }
        res = acc.accept_result(source="http", attempt_id=b["attempt_id"], claimed_tenant_id=TA, claimed_alert_id=alert_id,
                                claimed_job_id=b["job_id"], claimed_evidence_version=b["evidence_version"], raw=raw, fallback=None)
        self.assertTrue(res.handled, res.reason)
        return b

    def timeline(self, incident_id):
        from app.db.session import fetch_all

        return fetch_all("SELECT title, details, visibility FROM incident_timeline WHERE incident_id = %s::uuid AND title = 'TIA investigation note';", (incident_id,))

    def test_note_lands_on_the_incident_timeline_once_and_is_verified(self) -> None:
        from app.services import tia_ticket_note as tn

        a = self.alert()
        inc = self.incident(a)
        b = self.investigated(a)
        out = tn.write_investigation_note(b["attempt_id"])
        self.assertEqual(out["outcome"], "committed")
        self.assertTrue(out["verified"])
        rows = self.timeline(inc)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["visibility"], "internal")
        body = rows[0]["details"]
        for heading in ("Confirmed (from the stored record):", "Supported hypotheses (unverified):", "Unresolved:", "What TIA checked:", "Gaps:"):
            self.assertIn(heading, body)
        self.assertIn("a model view, not a finding", body)

    def test_retry_with_a_new_attempt_and_same_evidence_does_not_duplicate(self) -> None:
        from app.services import tia_effects
        from app.services import tia_ticket_note as tn

        a = self.alert()
        inc = self.incident(a)
        first = self.investigated(a)
        tn.write_investigation_note(first["attempt_id"])
        second = self.investigated(a)  # new attempt id, same evidence version
        self.assertNotEqual(first["attempt_id"], second["attempt_id"])
        self.assertEqual(first["evidence_version"], second["evidence_version"])
        out = tn.write_investigation_note(second["attempt_id"])
        self.assertEqual(out["outcome"], "already_committed")
        self.assertEqual(len(self.timeline(inc)), 1)
        hist = tia_effects.get("ticket_note", a, first["evidence_version"])["attempt_history"]
        self.assertEqual([h["attempt_id"] for h in hist], [first["attempt_id"], second["attempt_id"]])

    def test_lease_expiry_then_a_new_worker_does_not_duplicate_the_note(self) -> None:
        from app.db.session import execute
        from app.services import tia_jobs
        from app.services import tia_ticket_note as tn

        a = self.alert()
        inc = self.incident(a)
        tia_jobs.enqueue(alert_id=a, tenant_id=TA, severity="high", source="operator")
        old = tia_jobs.claim("old-worker")
        first = self.investigated(a)
        tn.write_investigation_note(first["attempt_id"])
        execute("UPDATE tia_jobs SET lease_expires_at = now() - interval '1 second' WHERE id = %s::uuid;", (old["id"],))
        tia_jobs.recover_expired()
        new = tia_jobs.claim("new-worker")
        self.assertEqual(new["alert_id"], a)
        self.assertNotEqual(new["attempts"], old["attempts"])
        second = self.investigated(a)
        self.assertNotEqual(first["attempt_id"], second["attempt_id"])
        out = tn.write_investigation_note(second["attempt_id"])
        self.assertEqual(out["outcome"], "already_committed")
        self.assertEqual(len(self.timeline(inc)), 1)
        self.assertFalse(tia_jobs.complete(old["id"], "old-worker"))
        self.assertTrue(tia_jobs.complete(new["id"], "new-worker"))

    def test_crash_after_commit_before_acknowledgement_does_not_duplicate(self) -> None:
        from app.services import tia_ticket_note as tn

        a = self.alert()
        inc = self.incident(a)
        b = self.investigated(a)
        tn.write_investigation_note(b["attempt_id"])  # committed; pretend the worker died before acking the job
        tn.write_investigation_note(b["attempt_id"])  # the job is redelivered with the same attempt
        self.assertEqual(len(self.timeline(inc)), 1)

    def test_a_crash_inside_the_write_leaves_nothing_behind(self) -> None:
        from app.services import tia_effects

        a = self.alert()
        inc = self.incident(a)

        def boom(cur):
            cur.execute("INSERT INTO incident_timeline (incident_id, event_type, visibility, title, details) VALUES (%s::uuid, 'comment', 'internal', 'TIA investigation note', 'x');", (inc,))
            raise RuntimeError("worker died mid-write")

        with self.assertRaises(RuntimeError):
            tia_effects.apply_local(kind="ticket_note", tenant_id=TA, alert_id=a, incident_id=inc, evidence_version="v1", attempt_id=None, content_hash="h", write=boom)
        self.assertEqual(len(self.timeline(inc)), 0)
        self.assertIsNone(tia_effects.get("ticket_note", a, "v1"))

    def test_concurrent_old_and_new_worker_produce_one_note(self) -> None:
        from app.services import tia_effects

        a = self.alert()
        inc = self.incident(a)
        results = []
        gate = threading.Barrier(2)

        def write(cur):
            cur.execute("INSERT INTO incident_timeline (incident_id, event_type, visibility, title, details) VALUES (%s::uuid, 'comment', 'internal', 'TIA investigation note', 'n') RETURNING id::text AS id;", (inc,))
            return cur.fetchone()["id"]

        def worker(att):
            gate.wait()
            results.append(tia_effects.apply_local(kind="ticket_note", tenant_id=TA, alert_id=a, incident_id=inc, evidence_version="v1", attempt_id=att, content_hash="h", write=write))

        ts = [threading.Thread(target=worker, args=(str(uuid.uuid4()),)) for _ in range(2)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(sorted(r["outcome"] for r in results), ["already_committed", "committed"])
        self.assertEqual(len(self.timeline(inc)), 1)

    def test_new_evidence_is_a_new_note(self) -> None:
        from app.db.session import execute
        from app.services import tia_ticket_note as tn

        a = self.alert()
        inc = self.incident(a)
        tn.write_investigation_note(self.investigated(a)["attempt_id"])
        execute("UPDATE security_alerts SET parent_command_line = 'powershell.exe -enc NEWEVIDENCE', updated_at = now() WHERE id = %s::uuid;", (a,))
        b2 = self.investigated(a, verdict="malicious")
        out = tn.write_investigation_note(b2["attempt_id"])
        self.assertEqual(out["outcome"], "committed", "a changed record must produce a fresh evidence version")
        self.assertEqual(len(self.timeline(inc)), 2)

    def test_a_human_decision_is_never_overwritten(self) -> None:
        from app.db.session import execute, fetch_one
        from app.services import tia_ticket_note as tn

        a = self.alert()
        inc = self.incident(a)
        b = self.investigated(a)
        execute("UPDATE incidents SET status = 'resolved', resolution_summary = 'Analyst: user confirmed the macro was a test.' WHERE id = %s::uuid;", (inc,))
        tn.write_investigation_note(b["attempt_id"])
        row = fetch_one("SELECT status, resolution_summary FROM incidents WHERE id = %s::uuid;", (inc,))
        self.assertEqual(row["status"], "resolved")
        self.assertEqual(row["resolution_summary"], "Analyst: user confirmed the macro was a test.")
        self.assertIn("incident status was not changed", self.timeline(inc)[0]["details"])

    def test_missing_incident_is_opened_so_the_note_is_not_lost(self) -> None:
        from app.db.session import fetch_one
        from app.services import tia_ticket_note as tn

        a = self.alert()
        self.assertIsNone(tn.incident_for_alert(TA, a))
        out = tn.write_investigation_note(self.investigated(a)["attempt_id"])
        self.assertEqual(out["outcome"], "committed", out)
        self.assertTrue(out.get("verified"))
        inc = tn.incident_for_alert(TA, a)
        self.assertIsNotNone(inc)
        self.assertTrue(str(inc["incident_number"]).startswith("INC-TIA-"))
        row = fetch_one(
            "SELECT title FROM incident_timeline WHERE incident_id = %s::uuid AND title = %s;",
            (inc["id"], tn.NOTE_TITLE),
        )
        self.assertIsNotNone(row)

    def test_failed_investigation_note_says_no_verdict(self) -> None:
        from app.services import tia_acceptance as acc
        from app.services import tia_ticket_note as tn

        a = self.alert()
        inc = self.incident(a)
        b = acc.open_attempt(alert_id=a, tenant_id=TA)
        acc.record_attempt_failure(attempt_id=b["attempt_id"], category="timeout", timed_out=True, error="client_timeout")
        tn.write_investigation_note(b["attempt_id"])
        body = self.timeline(inc)[0]["details"]
        self.assertIn("did not complete", body)
        self.assertIn("No verdict", body)


class FakeExternal:
    def __init__(self, *, lose_response=False, fail=False):
        self.notes = {}
        self.lose_response = lose_response
        self.fail = fail
        self.writes = 0

    def find_by_marker(self, ticket_ref, marker):
        return next((k for k, v in self.notes.items() if v[0] == marker), None)

    def add_note(self, ticket_ref, marker, text):
        from app.services import tia_effects

        if self.fail:
            raise ValueError("HTTP 400")
        self.writes += 1
        ref = f"note-{self.writes}"
        self.notes[ref] = (marker, text)
        if self.lose_response:
            raise tia_effects.OutcomeUnknown()
        return ref


class ExternalEffectTests(Base):
    def run_once(self, client, attempt):
        from app.services import tia_effects

        return tia_effects.apply_external(client=client, ticket_ref="CASE-1", tenant_id=TA, alert_id=self.a, evidence_version="v1", attempt_id=attempt, text="note")

    def setUp(self) -> None:
        super().setUp()
        self.a = self.alert()

    def age_lease(self):
        from app.db.session import execute

        execute("UPDATE tia_effects SET uncertain_since = now() - interval '1 hour' WHERE alert_id = %s::uuid;", (self.a,))

    def test_lost_response_is_reconciled_before_any_second_write(self) -> None:
        client = FakeExternal(lose_response=True)
        self.assertEqual(self.run_once(client, str(uuid.uuid4()))["outcome"], "uncertain")
        client.lose_response = False
        out = self.run_once(client, str(uuid.uuid4()))
        self.assertEqual(out["outcome"], "reconciled_existing")
        self.assertEqual(client.writes, 1)
        self.assertEqual(self.run_once(client, str(uuid.uuid4()))["outcome"], "already_committed")

    def test_a_live_lease_defers_a_second_worker(self) -> None:
        from app.db.session import execute

        client = FakeExternal()
        execute(
            "INSERT INTO tia_effects (logical_key, effect_kind, tenant_id, alert_id, evidence_version, status, uncertain_since) "
            "VALUES (%s, 'external_ticket_note', %s::uuid, %s::uuid, 'v1', 'uncertain', now());",
            (__import__("app.services.tia_effects", fromlist=["x"]).logical_key("external_ticket_note", self.a, "v1"), TA, self.a),
        )
        self.assertEqual(self.run_once(client, str(uuid.uuid4()))["outcome"], "in_flight_elsewhere")
        self.assertEqual(client.writes, 0)
        self.age_lease()  # the first worker died: after the lease, reconcile, then write
        self.assertEqual(self.run_once(client, str(uuid.uuid4()))["outcome"], "committed")
        self.assertEqual(client.writes, 1)

    def test_a_definite_failure_can_be_retried(self) -> None:
        client = FakeExternal(fail=True)
        self.assertEqual(self.run_once(client, str(uuid.uuid4()))["outcome"], "failed")
        client.fail = False
        self.assertEqual(self.run_once(client, str(uuid.uuid4()))["outcome"], "committed")
        self.assertEqual(client.writes, 1)


ROSTER = [{"name": "Test pager", "address": "test-destination@invalid.example"}]


class IntakeEscalationTests(Base):
    def test_off_by_default(self) -> None:
        from app.db.session import fetch_all
        from app.services import tia_acceptance as acc

        a = self.alert(severity="critical")
        with patch.dict("os.environ", {"TIA_PAGE_ON_INTAKE": ""}), patch("app.services.tia_schema.oncall_roster", return_value=ROSTER):
            acc.open_attempt(alert_id=a, tenant_id=TA)
        self.assertEqual(fetch_all("SELECT 1 FROM tia_notifications WHERE alert_id = %s::uuid;", (a,)), [])

    def test_a_critical_alert_pages_on_arrival_once_and_the_page_joins_its_review_item(self) -> None:
        from app.db.session import fetch_all
        from app.services import tia_acceptance as acc

        a = self.alert(severity="critical")
        with patch.dict("os.environ", {"TIA_PAGE_ON_INTAKE": "1"}), patch("app.services.tia_schema.oncall_roster", return_value=ROSTER):
            b = acc.open_attempt(alert_id=a, tenant_id=TA)
            acc.open_attempt(alert_id=a, tenant_id=TA)  # retry: same evidence, same page
            rows = fetch_all("SELECT message_body, review_item_id FROM tia_notifications WHERE alert_id = %s::uuid;", (a,))
            self.assertEqual(len(rows), 1)
            self.assertIn("investigation is still running", rows[0]["message_body"])
            self.assertIsNone(rows[0]["review_item_id"])
            acc.record_attempt_failure(attempt_id=b["attempt_id"], category="timeout", timed_out=True, error="client_timeout")
        rows = fetch_all("SELECT review_item_id FROM tia_notifications WHERE alert_id = %s::uuid;", (a,))
        self.assertTrue(rows and all(r["review_item_id"] for r in rows), "the arrival page is now settled with the review item")

    def test_a_high_alert_on_an_ordinary_asset_waits_for_the_investigation(self) -> None:
        from app.db.session import fetch_all
        from app.services import tia_acceptance as acc

        a = self.alert(severity="high")
        with patch.dict("os.environ", {"TIA_PAGE_ON_INTAKE": "1"}), patch("app.services.tia_schema.oncall_roster", return_value=ROSTER):
            acc.open_attempt(alert_id=a, tenant_id=TA)
        self.assertEqual(fetch_all("SELECT 1 FROM tia_notifications WHERE alert_id = %s::uuid;", (a,)), [])


if __name__ == "__main__":
    unittest.main()
