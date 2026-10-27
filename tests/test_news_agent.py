"""Offline tests for news_agent (injected fetch; no network)."""
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import news_agent, reports

ARTICLE_HTML = (
    '<html><head><meta property="og:title" content="Malaysia data centre boom '
    'attracts foreign investment"/><meta property="og:site_name" content="Test News"/>'
    '<meta name="twitter:title" content="Malaysia data centre boom"/></head>'
    '<body><article>'
    '<p>The government announced a new data centre hub in the east coast, with '
    'foreign direct investment of two billion ringgit over the next decade.</p>'
    '<p>Operators plan to launch the first phase within 18 months and expect '
    'strong demand for energy, cooling and maintenance services.</p>'
    '<p>Analysts said the expansion would create thousands of jobs and drive '
    'long-term growth in the technology and energy sectors.</p>'
    '</article></body></html>'
)


def route_fetch(url):
    """Serve the article for the article URL, macro JSON for evidence URLs."""
    if "worldbank" in url:
        if "GDP" in url or "NY.GDP" in url:
            return json.dumps([{"page": 1}, [{"indicator": {"value": "GDP growth (annual %)"},
                "date": "2024", "value": 5.1, "countryiso3code": "MYS"}]]).encode()
        if "FP.CPI" in url:
            return json.dumps([{"page": 1}, [{"indicator": {"value": "Inflation, CPI (annual %)"},
                "date": "2024", "value": 1.4, "countryiso3code": "MYS"}]]).encode()
        return json.dumps([{"page": 1}, [{"indicator": {"value": "Unemployment (% of labor force)"},
            "date": "2024", "value": 3.6, "countryiso3code": "MYS"}]]).encode()
    if "frankfurter" in url:
        return json.dumps({"base": "MYR", "date": "2026-10-27",
                           "rates": {"USD": 0.24, "SGD": 0.31, "AUD": 0.35}}).encode()
    if "crossref" in url:
        return json.dumps({"message": {"total-results": 1200,
                                       "items": [{"title": ["Data centres in SE Asia"], "DOI": "10.1/x"}]}}).encode()
    return ARTICLE_HTML.encode(), url


class FetchArticleTest(unittest.TestCase):
    def test_reads_title_body_source(self):
        art = news_agent.fetch_article("https://test.com/article", fetch=route_fetch)
        self.assertEqual(art["basis"], "evidence")
        self.assertIn("data centre boom", art["title"])
        self.assertEqual(art["source"], "Test News")
        self.assertGreaterEqual(len(art["paragraphs"]), 3)

    def test_thin_article(self):
        art = news_agent.fetch_article("https://x.com", fetch=lambda u: (b"<html><body>short</body></html>", "https://x.com"))
        self.assertIn(art["basis"], ("thin", "unavailable"))

    def test_unreachable(self):
        art = news_agent.fetch_article("https://down.com", fetch=lambda u: (_ for _ in ()).throw(OSError("nope")))
        self.assertEqual(art["basis"], "unavailable")


class ClassifyTest(unittest.TestCase):
    def test_long_horizon_growth(self):
        sig = news_agent.classify("Malaysia data centre hub, two billion ringgit "
                                  "investment over the next decade, long-term growth, "
                                  "launch first phase")
        self.assertIn(sig["horizon"], ("long", "both"))
        self.assertGreaterEqual(sig["growth_score"], 4)
        self.assertIn(sig["sector"], ("technology", "energy", "infrastructure"))

    def test_short_horizon(self):
        sig = news_agent.classify("Company posts strong Q3 earnings, dividend this week")
        self.assertIn(sig["horizon"], ("short", "both"))

    def test_low_potential(self):
        sig = news_agent.classify("weather is nice today")
        self.assertEqual(sig["potential_class"], "low")


class PlanTest(unittest.TestCase):
    def _plan(self, **kw):
        art = news_agent.fetch_article("https://test.com/a", fetch=route_fetch)
        return news_agent.implementation_plan(art, topic="data centre hub", **kw)

    def test_all_sections_present(self):
        plan = self._plan(band="medium")
        for key in ("sector", "horizon", "signals", "summary", "evidence", "flow",
                    "budget", "risks", "steps", "m_and_a", "joint_venture",
                    "investment", "marketing"):
            self.assertIn(key, plan)
        self.assertEqual(plan["budget"]["band"], "medium")
        self.assertGreater(plan["budget"]["total"], 0)
        self.assertTrue(plan["review_required"])

    def test_macro_evidence_attached(self):
        plan = self._plan(band="small", with_macro=True)
        ev = plan["evidence"]["macro"]
        self.assertTrue(any(m.get("basis") == "evidence" and m.get("source") == "world_bank"
                            for m in ev))

    def test_macro_off(self):
        plan = self._plan(band="small", with_macro=False)
        self.assertEqual(plan["evidence"]["macro"], [])

    def test_investment_routes_filtered_by_band(self):
        plan = self._plan(band="large")
        fits = {r["route"] for r in plan["investment"]["routes"]}
        self.assertTrue(any("venture" in r.lower() for r in fits))

    def test_risks_sorted_and_scored(self):
        plan = self._plan(band="medium")
        scores = [r["score"] for r in plan["risks"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(all("mitigation" in r for r in plan["risks"]))

    def test_mna_jv_marketing_have_steps(self):
        plan = self._plan(band="small")
        self.assertTrue(plan["m_and_a"]["steps"])
        self.assertTrue(plan["joint_venture"]["structures"])
        self.assertTrue(plan["marketing"]["channels"])

    def test_summary_is_evidence_based(self):
        plan = self._plan(band="small")
        self.assertIn("data centre", plan["summary"].lower())


class DossierTest(unittest.TestCase):
    def test_sections_order_and_new_blocks(self):
        art = news_agent.fetch_article("https://test.com/a", fetch=route_fetch)
        plan = news_agent.implementation_plan(art, topic="data centre hub", band="medium")
        dossier = news_agent.news_dossier(plan, [])
        keys = list(dossier["sections"].keys())
        for required in ("opportunity", "signals", "market_evidence", "flow",
                         "financial_forecast", "investment", "merger_jv", "marketing",
                         "risk", "plan"):
            self.assertIn(required, keys)
        # M&A + JV merged section contains both notes
        mj = dossier["sections"]["merger_jv"]["content"]
        self.assertTrue(any("M&A" in line for line in mj))
        self.assertTrue(any("JV" in line for line in mj))
        # evidence label present per section
        self.assertTrue(all(s.get("label") in ("verified", "estimated", "assumed", "unavailable")
                            for s in dossier["sections"].values()))

    def test_news_items_rendered(self):
        art = news_agent.fetch_article("https://test.com/a", fetch=route_fetch)
        plan = news_agent.implementation_plan(art, topic="x", band="small")
        items = [{"source": "FMT", "title": "Some headline", "body_readable": True}]
        dossier = news_agent.news_dossier(plan, items)
        self.assertIn("Headlines scanned", dossier["sections"]["news_scan"]["content"][0])


class PlanFromResultTest(unittest.TestCase):
    def _result(self):
        return {
            "plan": {"query": "solar maintenance Malaysia", "country": "Malaysia",
                     "capital": "small"},
            "candidates": [
                {"title": "Malaysia solar farm expansion creates demand for maintenance",
                 "source_url": "https://test.com/solar", "verification": {"verified": True}},
                {"title": "Solar panel cleaning services grow in the region",
                 "source_url": "https://test.com/clean", "verification": {"verified": False}},
            ],
            "gap_hits": {"competition": 2, "regulation": 1},
        }

    def test_builds_plan(self):
        plan = news_agent.plan_from_result(self._result())
        self.assertEqual(plan["country"], "Malaysia")
        self.assertEqual(plan["budget"]["band"], "small")
        self.assertIn("solar", plan["topic"].lower())
        self.assertTrue(plan["m_and_a"]["options"])

    def test_empty_result_raises(self):
        with self.assertRaises(ValueError):
            news_agent.plan_from_result({"candidates": []})


class ReportTest(unittest.TestCase):
    def test_generate_news_report_writes_docx_and_charts(self):
        art = news_agent.fetch_article("https://test.com/a", fetch=route_fetch)
        plan = news_agent.implementation_plan(art, topic="data centre hub", band="medium")
        dossier = news_agent.news_dossier(plan, [])
        with tempfile.TemporaryDirectory() as d:
            res = reports.generate_news_report(dossier, plan, d)
            self.assertTrue(os.path.exists(res["docx"]))
            self.assertGreater(os.path.getsize(res["docx"]), 2000)
            chart_names = {os.path.basename(c) for c in res["charts"]}
            self.assertEqual(chart_names, {"flow.png", "budget.png", "risk.png"})
            for chart in ("flow.png", "budget.png", "risk.png"):
                self.assertTrue(any(c.endswith(chart) for c in res["charts"]))
            # DOCX is a valid zip with the expected parts
            with zipfile.ZipFile(res["docx"]) as zf:
                names = zf.namelist()
                self.assertIn("word/document.xml", names)
                self.assertIn("[Content_Types].xml", names)
                self.assertTrue(any(n.startswith("word/media/") for n in names))
            with zipfile.ZipFile(res["docx"]) as zf:
                doc = zf.read("word/document.xml").decode("utf-8", "replace")
            for needle in ("INVESTMENT", "MERGER", "MARKETING", "RISK"):
                self.assertIn(needle, doc.upper())


if __name__ == "__main__":
    unittest.main()
