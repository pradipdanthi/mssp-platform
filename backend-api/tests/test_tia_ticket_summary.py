"""Ticket summary: case-specific, facts separated from hypotheses, scoped, deterministic."""

from __future__ import annotations

import unittest

import tia_testenv
from test_tia_conversation import TA, TB, ConversationBase


class TicketSummaryTests(ConversationBase):
    def get(self, who, key):
        return self.client.get(f"/admin/soc-console/alerts/{self.ids[key]}/ticket-summary", headers=self.users[who]["headers"])

    def test_two_different_cases_get_different_specific_summaries(self) -> None:
        a = self.get("analyst", "a_crit_old").json()
        b = self.get("analyst", "a_crit_new").json()
        self.assertIn("HOST-A1", a["headline"])
        self.assertIn("HOST-A2", b["headline"])
        self.assertNotEqual(a["summary_key"], b["summary_key"])
        self.assertIn("Credential dumping", a["text"])
        self.assertNotIn("Credential dumping", b["text"])

    def test_missing_evidence_is_listed_not_filled_in(self) -> None:
        s = self.get("analyst", "a_crit_old").json()
        self.assertTrue(any("No parent process" in n for n in s["not_known"]))
        self.assertNotRegex(s["text"], r"(?i)\broot cause\b")

    def test_a_model_assessment_appears_only_as_an_unverified_hypothesis(self) -> None:
        from app.db.session import execute

        execute("UPDATE security_alerts SET ai_verdict='BENIGN_FALSE_POSITIVE', ai_confidence=97, ai_likely_attack_type='Credential Access' WHERE id=%s::uuid;", (self.ids["a_crit_old"],))
        s = self.get("analyst", "a_crit_old").json()
        self.assertTrue(any("not a finding" in h for h in s["hypotheses"]))
        self.assertFalse(any("BENIGN" in f for f in s["facts"]))
        self.assertEqual(s["disposition"]["value"], "unset")  # a model "Benign" is not a disposition
        self.assertIn("Analyst review now", s["next_step"])  # critical + no verified disposition

    def test_the_same_record_gives_the_same_key_so_ticket_updates_can_be_idempotent(self) -> None:
        self.assertEqual(self.get("analyst", "a_crit_new").json()["summary_key"], self.get("analyst", "a_crit_new").json()["summary_key"])

    def test_another_tenants_alert_and_customers_are_refused(self) -> None:
        self.assertEqual(self.client.get("/admin/soc-console/alerts/00000000-0000-0000-0000-00000000dead/ticket-summary", headers=self.users["analyst"]["headers"]).status_code, 404)
        self.assertIn(self.get("customer", "a_crit_old").status_code, (401, 403))


if __name__ == "__main__":
    unittest.main()
