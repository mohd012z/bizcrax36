"""Offline tests for Agentic Research V2: plan, discovery, verify, score, stages."""
import unittest
from datetime import datetime, timezone
from email.utils import format_datetime
from urllib.parse import unquote, parse_qs, urlparse
from xml.etree import ElementTree

from backend import research_v2


def rss_bytes(items):
    parts = ['<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>']
    for title, link, when in items:
        parts.append('<item><title>%s</title><link>%s</link><pubDate>%s</pubDate></item>'
                     % (title, link, when))
    parts.append('</channel></rss>')
    return "".join(parts).encode()


def make_fetch(by_query):
    """Return a fetch(target) that routes by the ?q= parameter (case-insensitive)."""
    keys = {q.lower(): items for q, items in by_query.items()}
    def fetch(target):
        q = unquote(parse_qs(urlparse(target).query).get("q", [""])[0]).lower()
        items = keys.get(q)
        if items is None:
            raise OSError("no fixture for query %r" % q)
        return rss_bytes(items)
    return fetch


NOW = format_datetime(datetime(2026, 10, 27, 9, 0, tzinfo=timezone.utc))
OLD = format_datetime(datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc))

# link -> title; page_fetch returns a page containing the link's own headline,
# mirroring "fetch the source and check the claimed title is actually there".
LINK_TITLES = {
    "https://example.org/solar-demand": "Solar panel maintenance demand surges in Malaysia",
    "https://example.org/solar-demand-dup": "Solar panel maintenance demand surges in Malaysia",
    "https://example.org/sme-suppliers": "Malaysia SMEs seek solar maintenance suppliers",
    "https://example.org/programme": "Government solar efficiency programme expanded 2026",
    "https://example.org/tender": "Tender: solar farm maintenance services",
    "https://example.org/cost-guide": "Low-cost solar maintenance startup guide",
    "https://example.org/pricing": "Competitor pricing survey solar services Malaysia",
    "https://example.org/licence": "Electricity licence requirements solar contractors",
    "https://example.org/survey": "Customer survey: solar maintenance demand 2026",
    "https://example.org/efficiency": "Energy efficiency retrofit market grows",
}

def fixture_fetch():
    return make_fetch({
        "solar maintenance malaysia market demand": [
            ("Solar panel maintenance demand surges in Malaysia", "https://example.org/solar-demand", NOW),
            ("Solar panel maintenance demand surges in Malaysia", "https://example.org/solar-demand-dup", NOW),
        ],
        "solar maintenance malaysia sme supplier opportunities": [
            ("Malaysia SMEs seek solar maintenance suppliers", "https://example.org/sme-suppliers", NOW),
        ],
        "solar maintenance malaysia government programme": [
            ("Government solar efficiency programme expanded 2026", "https://example.org/programme", OLD),
        ],
        "solar maintenance malaysia procurement tender": [
            ("Tender: solar farm maintenance services", "https://example.org/tender", NOW),
        ],
        "solar maintenance malaysia low startup cost": [
            ("Low-cost solar maintenance startup guide", "https://example.org/cost-guide", NOW),
        ],
        "energy efficiency malaysia business": [
            ("Energy efficiency retrofit market grows", "https://example.org/efficiency", NOW),
        ],
        "solar maintenance malaysia competitors pricing": [
            ("Competitor pricing survey solar services Malaysia", "https://example.org/pricing", NOW),
        ],
        "solar maintenance malaysia licence registration requirement": [
            ("Electricity licence requirements solar contractors", "https://example.org/licence", NOW),
        ],
        "solar maintenance malaysia customer demand survey": [
            ("Customer survey: solar maintenance demand 2026", "https://example.org/survey", NOW),
        ],
    })


def page_fetch():
    def fetch(target):
        title = LINK_TITLES.get(target)
        if title is None:
            return "<html><body>unrelated page</body></html>"
        return ("<html><head><script>var a='zzzzqqq'</script></head>"
                "<body><h1>%s</h1><p>Malaysia solar maintenance market analysis.</p></body></html>"
                % title)
    return fetch


class PlanTests(unittest.TestCase):
    def test_plan_two_rounds_with_gap_queries(self):
        task = research_v2.plan("solar maintenance", "Malaysia", "micro")
        self.assertEqual(len(task["rounds"]), 2)
        self.assertGreaterEqual(len(task["rounds"][0]), 4)
        self.assertEqual(len(task["rounds"][1]), 3)
        self.assertTrue(any("competitors" in q for q in task["rounds"][1]))
        self.assertTrue(any("licence" in q for q in task["rounds"][1]))
        self.assertIn("low startup cost", " ".join(task["rounds"][0]))

    def test_plan_rejects_unknown_capital(self):
        with self.assertRaises(ValueError):
            research_v2.plan("solar", "Malaysia", "huge")

    def test_plan_requires_words(self):
        with self.assertRaises(ValueError):
            research_v2.plan("the and for", "Malaysia")


class BandTests(unittest.TestCase):
    def test_band_boundaries(self):
        self.assertEqual(research_v2.band_of(0), "micro")
        self.assertEqual(research_v2.band_of(9_999), "micro")
        self.assertEqual(research_v2.band_of(10_000), "small")
        self.assertEqual(research_v2.band_of(250_000), "medium")
        self.assertEqual(research_v2.band_of(2_000_000), "large")
        self.assertEqual(research_v2.band_of(10_000_000), "large")


class VerifyTests(unittest.TestCase):
    def test_verified_on_title_match(self):
        candidate = {"title": "Solar panel maintenance demand surges in Malaysia",
                     "source_url": "https://example.org/solar-demand"}
        result = research_v2.verify(candidate, fetch=page_fetch())
        self.assertTrue(result["verified"])
        self.assertGreaterEqual(result["match_ratio"], 0.6)
        self.assertIn("retrieved_at", result)

    def test_unverified_on_unrelated_page(self):
        candidate = {"title": "Solar panel maintenance demand surges in Malaysia",
                     "source_url": "https://other.example/page"}
        result = research_v2.verify(candidate, fetch=page_fetch())
        self.assertFalse(result["verified"])
        self.assertEqual(result["reason"], "insufficient_title_match")

    def test_no_source_url(self):
        result = research_v2.verify({"title": "Some headline here today", "source_url": None},
                                    fetch=page_fetch())
        self.assertFalse(result["verified"])
        self.assertEqual(result["reason"], "no_source_url")


class ScoreTests(unittest.TestCase):
    def test_weighted_total_and_basis_labels(self):
        candidate = {"title": "solar maintenance malaysia", "source_url": "https://x.org/a",
                     "published_at": NOW}
        result = research_v2.score(candidate, ["solar", "maintenance"], "micro",
                                   {"competition": 1, "regulation": 1}, verified_count=1)
        self.assertGreaterEqual(result["total"], 0)
        self.assertLessEqual(result["total"], 100)
        for key, weight in research_v2.WEIGHTS.items():
            self.assertIn(key, result["metrics"])
            self.assertEqual(result["metrics"][key]["basis"] in ("evidence", "assumed"), True)
            self.assertEqual(result["weights"][key], weight)
        expected = int(round(sum(
            research_v2.WEIGHTS[k] * result["metrics"][k]["value"] for k in research_v2.WEIGHTS) / 100.0))
        self.assertEqual(result["total"], max(0, min(100, expected)))

    def test_capital_band_affects_score(self):
        candidate = {"title": "solar maintenance malaysia", "source_url": "https://x.org/a",
                     "published_at": NOW}
        gaps = {"competition": 0, "regulation": 0}
        low = research_v2.score(candidate, [], "micro", gaps, 0)["total"]
        high = research_v2.score(candidate, [], "large", gaps, 0)["total"]
        self.assertGreater(low, high)


class ResearchPipelineTests(unittest.TestCase):
    def test_full_offline_pipeline(self):
        fetch = fixture_fetch()
        result = research_v2.research("solar maintenance", "Malaysia", capital="micro",
                                      fetch=fetch, verify_fetch=page_fetch(),
                                      max_queries=6, verify_top=3)
        self.assertEqual(result["schema_version"], 2)
        self.assertGreaterEqual(len(result["candidates"]), 4)
        self.assertEqual(len(result["errors"]), 0)
        # dedup: duplicate title appears once
        titles = [c["title"] for c in result["candidates"]]
        self.assertEqual(len(titles), len(set(titles)))
        # gap hits recorded
        self.assertEqual(result["gap_hits"]["competition"], 1)
        self.assertEqual(result["gap_hits"]["regulation"], 1)
        # verification ran and at least one source verified
        verified = [c for c in result["candidates"] if c.get("verification", {}).get("verified")]
        self.assertGreaterEqual(len(verified), 1)
        # sorted by score desc
        scores = [c["score"]["total"] for c in result["candidates"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertIn("review_required", result["notice"])

    def test_stages_reported_in_order(self):
        stages = []
        research_v2.research("solar maintenance", "Malaysia", capital="all",
                             fetch=fixture_fetch(), verify_fetch=page_fetch(),
                             on_stage=lambda s: stages.append(s))
        self.assertEqual(stages[:3], ["researching", "verifying", "scoring"])

    def test_source_errors_are_isolated(self):
        def flaky(target):
            q = unquote(parse_qs(urlparse(target).query).get("q", [""])[0])
            if "tender" in q:
                raise OSError("timeout")
            return rss_bytes([("Solar maintenance demand grows", "https://example.org/ok", NOW)])
        result = research_v2.research("solar maintenance", "Malaysia", fetch=flaky,
                                      verify_fetch=page_fetch(), max_queries=6)
        self.assertGreaterEqual(len(result["errors"]), 1)
        self.assertTrue(all(e["error"] == "OSError" for e in result["errors"]))
        self.assertGreaterEqual(len(result["candidates"]), 1)

    def test_empty_results_do_not_crash(self):
        def empty(target):
            return rss_bytes([])
        result = research_v2.research("solar maintenance", "Malaysia", fetch=empty,
                                      verify_fetch=page_fetch(), max_queries=6)
        self.assertEqual(result["candidates"], [])
        self.assertIn("sector", result["plan"])


if __name__ == "__main__":
    unittest.main()
