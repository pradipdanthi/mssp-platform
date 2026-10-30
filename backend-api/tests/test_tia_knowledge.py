"""Knowledge helpers: labels, component resolution, no dashboard substitution.

These are unit checks of the catalogue and report shape. Live converse coverage
lives in test_tia_conversation.py using paraphrases, not a single rehearsed string.
"""

from __future__ import annotations

import unittest

import tia_testenv


class KnowledgeCatalogueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        tia_testenv.require_test_modules()

    def test_resolve_named_and_alias_components(self) -> None:
        from app.services.tia_knowledge import resolve_component

        self.assertEqual(resolve_component("where does shuffle run"), "shuffle")
        self.assertEqual(resolve_component("the hive case manager"), "thehive")
        self.assertEqual(resolve_component("admin portal on 3000"), "admin_portal")
        self.assertEqual(resolve_component("no idea", source_tool="wazuh"), "wazuh")
        self.assertIsNone(resolve_component("something unnamed"))

    def test_report_separates_observed_from_hypothesis(self) -> None:
        from app.services.tia_knowledge import format_report

        r = format_report(
            "Title",
            ["tcp connect succeeded"],
            ["VM 101 is the manager"],
            ["could be a quiet estate"],
            ["auth not checked"],
            spoken="Reachable is not ingest.",
        )
        self.assertIn("Observed:", r["answer"])
        self.assertIn("Hypothesis (not a finding):", r["answer"])
        self.assertIn("Not verified / not checked:", r["answer"])
        self.assertEqual(r["spoken_answer"], "Reachable is not ingest.")


if __name__ == "__main__":
    unittest.main()
