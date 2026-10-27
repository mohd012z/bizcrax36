"""Offline tests for evidence_sources (injected single-arg fetch; no network)."""
import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.pop("OPEN_SANCTIONS_API_KEY", None)
os.environ.pop("OPEN_CORPORATES_API_KEY", None)

from backend import evidence_sources as es


def wb_payload(value, date="2024", label="GDP growth (annual %)", code="MYS"):
    return json.dumps([{"page": 1},
                       [{"indicator": {"value": label}, "date": date,
                         "value": value, "countryiso3code": code}]]).encode()


class WorldBankTest(unittest.TestCase):
    def test_known_country_evidence(self):
        def fake(url):
            if "worldbank" not in url:
                self.fail("unexpected url " + url)
            if "NY.GDP.MKTP.KD.ZG" in url:
                return wb_payload(5.17)
            if "FP.CPI.TOTL.ZG" in url:
                return wb_payload(1.38, label="Inflation, CPI (annual %)")
            return wb_payload(3.7, label="Unemployment (% of labor force)")
        rows = es.world_bank("Malaysia", fetch=fake)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(r["basis"] == "evidence" for r in rows))
        self.assertEqual(rows[0]["value"], 5.17)
        self.assertEqual(rows[0]["country"], "MYS")

    def test_unknown_country_unavailable(self):
        rows = es.world_bank("Atlantis")
        self.assertEqual(rows[0]["basis"], "unavailable")

    def test_network_error_unavailable(self):
        def boom(url):
            raise OSError("down")
        rows = es.world_bank("Malaysia", fetch=boom)
        self.assertTrue(all(r["basis"] == "unavailable" for r in rows))

    def test_null_value_unavailable(self):
        def fake(url):
            return wb_payload(None)
        rows = es.world_bank("Malaysia", fetch=fake)
        self.assertTrue(all(r["basis"] == "unavailable" for r in rows))


class FXTest(unittest.TestCase):
    def test_frankfurter_ok(self):
        def fake(url):
            self.assertIn("frankfurter", url)
            return json.dumps({"base": "MYR", "date": "2026-10-27",
                               "rates": {"USD": 0.24, "SGD": 0.31, "AUD": 0.35}}).encode()
        rows = es.exchange_rates("MYR", fetch=fake)
        self.assertTrue(all(r["basis"] == "evidence" for r in rows))
        self.assertEqual(len(rows), 3)
        self.assertIn("0.24", rows[0]["label"])

    def test_frankfurter_down_fails_over_to_currency_api(self):
        def fake(url):
            if "frankfurter" in url:
                raise OSError("down")
            return json.dumps({"date": "2026-10-27",
                               "myr": {"usd": 4.15, "sgd": 3.2, "aud": 2.86}}).encode()
        rows = es.exchange_rates("MYR", fetch=fake)
        self.assertTrue(all(r["source"] == "currency_api_fx" for r in rows))

    def test_both_down_unavailable(self):
        def fake(url):
            raise OSError("down")
        rows = es.exchange_rates("MYR", fetch=fake)
        self.assertEqual(rows[0]["basis"], "unavailable")


class CrossrefTest(unittest.TestCase):
    def test_ok(self):
        def fake(url):
            self.assertIn("crossref", url)
            return json.dumps({"message": {"total-results": 42,
                                           "items": [{"title": ["Paper A"], "DOI": "10.1/a"}]}}).encode()
        rows = es.research_literature("data centre", fetch=fake)
        self.assertEqual(rows[0]["total_results"], 42)
        self.assertEqual(rows[1]["detail"], "Paper A")

    def test_down(self):
        def fake(url):
            raise ValueError("bad xml")
        rows = es.research_literature("test", fetch=fake)
        self.assertEqual(rows[0]["basis"], "unavailable")


class KeyGatedTest(unittest.TestCase):
    def test_without_key_unavailable(self):
        self.assertEqual(es.open_sanctions("x")[0]["basis"], "unavailable")
        self.assertEqual(es.open_corporates("x")[0]["basis"], "unavailable")


class FetchAllTest(unittest.TestCase):
    def test_aggregates_and_records_errors(self):
        def fake(url):
            if "worldbank" in url:
                return wb_payload(4.9)
            if "frankfurter" in url:
                return json.dumps({"base": "MYR", "rates": {"USD": 0.24}}).encode()
            if "crossref" in url:
                return json.dumps({"message": {"total-results": 1, "items": []}}).encode()
            raise OSError("down")  # sanctions/corporates would fail here if keyed
        records, errors = es.fetch_all("test", "Malaysia", fetch=fake)
        sources = {r["source"] for r in records}
        self.assertIn("world_bank", sources)
        self.assertIn("frankfurter_fx", sources)
        self.assertIn("crossref", sources)
        self.assertIn("open_sanctions", sources)  # no key -> unavailable row
        self.assertIn("open_corporates", sources)

    def test_never_raises_on_total_failure(self):
        def fake(url):
            raise OSError("down")
        records, errors = es.fetch_all("test", "Malaysia", fetch=fake)
        self.assertTrue(all(r["basis"] == "unavailable" for r in records))
        self.assertGreater(len(errors), 0)


if __name__ == "__main__":
    unittest.main()
