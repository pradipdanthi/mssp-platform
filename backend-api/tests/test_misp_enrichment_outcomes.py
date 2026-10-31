"""Targeted MISP enrichment outcomes (mocked vs live).

Mocked checks below are labeled MOCKED. They do not contact MISP.
Live adapter lookups belong in operator verification, not this file.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services import misp_client


class TestMispRestSearchOutcomesMocked(unittest.TestCase):
    """MOCKED: match / no-match / lookup-failed without touching MISP."""

    def test_mocked_match_found_exact_value(self) -> None:
        payload = {
            "response": {
                "Attribute": [
                    {
                        "id": "1",
                        "type": "ip-dst",
                        "value": "185.220.101.45",
                        "event_id": "1",
                        "timestamp": "1785607324",
                        "comment": "APT29: C2 infrastructure",
                    },
                    {
                        "id": "2",
                        "type": "domain",
                        "value": "update-cdn-secure.net",
                        "event_id": "1",
                        "timestamp": "1785607324",
                        "comment": "FIN7",
                    },
                ]
            }
        }
        with patch.object(misp_client, "_post", return_value=payload):
            hits = misp_client.rest_search_attributes(value="185.220.101.45")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["id"], "1")
        self.assertEqual(hits[0]["event_id"], "1")
        # Match found = supporting intelligence, not an automatic verdict.
        self.assertIn("comment", hits[0])

    def test_mocked_no_match_when_bridge_returns_unrelated(self) -> None:
        payload = {
            "response": {
                "Attribute": [
                    {
                        "id": "1",
                        "type": "ip-dst",
                        "value": "185.220.101.45",
                        "event_id": "1",
                        "timestamp": "1785607324",
                        "comment": "APT29: C2 infrastructure",
                    }
                ]
            }
        }
        with patch.object(misp_client, "_post", return_value=payload):
            hits = misp_client.rest_search_attributes(value="192.168.0.99")
        self.assertEqual(hits, [])
        # No match = no matching intelligence, not evidence of benign activity.

    def test_mocked_lookup_failed_unavailable(self) -> None:
        with patch.object(
            misp_client, "_post", side_effect=misp_client.MispClientError("MISP HTTP 503")
        ):
            with self.assertRaises(misp_client.MispClientError):
                misp_client.rest_search_attributes(value="185.220.101.45")
        # Lookup failed/unavailable = enrichment incomplete.


if __name__ == "__main__":
    unittest.main()
