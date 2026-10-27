import unittest
from backend.agentic_research import plan, research, score

RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>Malaysia SME automation programme</title><link>https://news.google.com/a</link><pubDate>Mon, 26 Oct 2026 00:00:00 GMT</pubDate></item>
<item><title>Malaysia SME automation programme</title><link>https://news.google.com/a</link></item>
<item><title>Industrial maintenance suppliers</title><link>https://news.google.com/b</link></item>
</channel></rss>"""

class ResearchTests(unittest.TestCase):
    def test_plan_specific_to_user_query(self):
        result = plan("aerospace training suppliers")
        self.assertEqual(result["sector"], "aerospace")
        self.assertTrue(all("Malaysia" in q for q in result["subqueries"]))

    def test_empty_query_rejected(self):
        with self.assertRaises(ValueError):
            plan("the and")

    def test_deduplicates_across_queries(self):
        result = research("SME automation", fetch=lambda _: RSS)
        self.assertEqual(len(result["candidates"]), 2)
        self.assertTrue(all(x["status"] == "review_required" for x in result["candidates"]))
        self.assertTrue(all(not x["verification"]["commercial_demand_confirmed"] for x in result["candidates"]))

    def test_source_failure_is_reported(self):
        def broken(_):
            raise OSError("offline")
        result = research("aviation training", fetch=broken)
        self.assertEqual(result["candidates"], [])
        self.assertTrue(result["errors"])

    def test_scores_are_preliminary(self):
        self.assertEqual(score({"title": "SME automation", "source_url": "https://example.org"}, ["sme"])["score_type"], "preliminary_heuristic")

if __name__ == "__main__":
    unittest.main()
