"""Typed greetings must classify as greeting, not fall through to unrecognised."""

from __future__ import annotations

import unittest

from app.services import tia_intents


class TiaGreetingIntentTests(unittest.TestCase):
    def test_greeting_variants(self):
        for text in ("Hi Tia", "HI tia", "Hi, Tia.", "hello", "Hey TIA"):
            self.assertEqual(tia_intents.classify(text), tia_intents.GREETING, text)

    def test_execution_not_stolen_by_greeting(self):
        self.assertEqual(
            tia_intents.classify("hi, please investigate this"),
            tia_intents.EXECUTION,
        )


if __name__ == "__main__":
    unittest.main()
