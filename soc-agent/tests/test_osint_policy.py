import unittest
from unittest.mock import patch

from app.core import osint


class OsintPolicyTests(unittest.TestCase):
    def test_no_policy_means_no_outbound_lookup(self) -> None:
        with patch.object(osint.httpx, "Client") as client:
            out = osint.enrich_osint({"source_ip": "8.8.8.8", "raw": {}})
        client.assert_not_called()
        self.assertEqual(out["source_ip"]["skipped"], "customer_has_not_authorised_ip_reputation")

    def test_private_addresses_are_never_sent_even_when_authorised(self) -> None:
        with patch.object(osint.httpx, "Client") as client:
            out = osint.enrich_osint({"source_ip": "10.1.2.3", "destination_ip": "192.168.0.5", "raw": {"research_policy": {"ip_reputation": ["otx"]}}})
        client.assert_not_called()
        self.assertEqual(out["source_ip"]["skipped"], "not_a_public_address")
        self.assertEqual(out["destination_ip"]["skipped"], "not_a_public_address")

    def test_only_the_authorised_provider_is_contacted(self) -> None:
        calls = []

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def get(self, url, **k):
                calls.append(url)

                class R:
                    status_code = 200

                    @staticmethod
                    def json():
                        return {"pulse_info": {"count": 0}}

                return R()

        with patch.object(osint.httpx, "Client", FakeClient), patch.dict("os.environ", {"ABUSEIPDB_API_KEY": "x"}):
            osint.enrich_osint({"source_ip": "8.8.8.8", "raw": {"research_policy": {"ip_reputation": ["otx"]}}})
        self.assertTrue(calls)
        self.assertTrue(all("otx.alienvault.com" in u for u in calls))


if __name__ == "__main__":
    unittest.main()
