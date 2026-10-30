"""Intent families: recommendation is not execution. No database."""

from __future__ import annotations

import unittest

from app.services import tia_intents as intents


class ClassifyTests(unittest.TestCase):
    def test_happened_here_is_assessment(self) -> None:
        self.assertEqual(intents.classify("What do you think happened here?"), intents.ASSESSMENT)
        self.assertEqual(intents.classify("What happened here?"), intents.ASSESSMENT)

    def test_actually_critical_is_assessment(self) -> None:
        self.assertEqual(intents.classify("Is this actually critical?"), intents.ASSESSMENT)

    def test_investigate_next_is_recommendation_not_execution(self) -> None:
        self.assertEqual(intents.classify("What should we investigate next?"), intents.RECOMMENDATION)
        self.assertEqual(intents.classify("Investigate this"), intents.EXECUTION)
        self.assertEqual(intents.classify("Please investigate"), intents.EXECUTION)

    def test_status_is_not_a_new_job(self) -> None:
        self.assertEqual(intents.classify("What investigation have you done?"), intents.STATUS)
        self.assertEqual(intents.classify("investigation status"), intents.STATUS)

    def test_wazoo_resolves_to_wazuh_with_shuffle(self) -> None:
        self.assertEqual(
            set(intents.engines_in_text("Wazoo and Shuffle actually processing work")),
            {"wazuh", "shuffle"},
        )


if __name__ == "__main__":
    unittest.main()
