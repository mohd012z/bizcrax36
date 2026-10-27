"""Offline tests for the 360-degree dossier and research queue."""
import json
import unittest
from datetime import datetime, timezone

from backend import research_v2
from backend.dossier import build as build_dossier, summary_text
from backend.research_queue import run_job, is_duplicate, validate_topic, job_id, diagnostics_line


def result_fixture():
    return {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "plan": {"query": "solar maintenance", "country": "Malaysia", "capital": "micro",
                 "sector": "energy", "rounds": []},
        "candidates": [
            {"id": "a1", "title": "Solar panel maintenance demand surges in Malaysia",
             "source_url": "https://example.org/solar", "published_at": None,
             "verification": {"verified": True, "retrieved_at": "x"},
             "score": {"total": 71, "metrics": {}, "weights": {}}},
            {"id": "a2", "title": "Tender: solar farm maintenance services",
             "source_url": "https://example.org/tender", "published_at": None,
             "verification": {"verified": False},
             "score": {"total": 55, "metrics": {}, "weights": {}}},
        ],
        "errors": [{"subquery": "q", "error": "OSError"}],
        "gap_hits": {"competition": 1, "regulation": 0},
        "notice": "leads only",
    }


class DossierTests(unittest.TestCase):
    def test_all_sections_present_and_labeled(self):
        d = build_dossier(result_fixture())
        self.assertEqual(len(d["sections"]), 14)
        for key, meta in d["sections"].items():
            self.assertIn("title", meta)
            self.assertIn("label", meta)
            self.assertIn(meta["label"], ("verified", "estimated", "assumed", "unavailable"))
            self.assertIsInstance(meta.get("content", []), list)
        self.assertEqual(d["top_candidate_id"], "a1")
        self.assertEqual(d["capital_band"], "micro")

    def test_funding_section_lists_real_programs(self):
        d = build_dossier(result_fixture())
        text = " ".join(d["sections"]["funding_investment"]["content"])
        self.assertIn("SME Bank", text)
        self.assertIn("MIDA", text)
        self.assertIn("Seda".upper(), text.upper())

    def test_summary_text_compact_and_labeled(self):
        d = build_dossier(result_fixture())
        s = summary_text(d, result_fixture())
        self.assertLessEqual(len(s), 3900)
        self.assertIn("360", s)
        self.assertIn("Solar panel maintenance demand surges in Malaysia", s)
        self.assertIn("ASSUMED", s.upper())

    def test_summary_handles_empty_result(self):
        result = result_fixture()
        result["candidates"] = []
        d = build_dossier(result)
        s = summary_text(d, result)
        self.assertIn("TOP LEADS", s)
        self.assertEqual(d["top_candidate_id"], None)


class QueueTests(unittest.TestCase):
    def test_job_id_stable_and_short(self):
        a = job_id("solar maintenance", "micro", "Malaysia")
        b = job_id("Solar Maintenance", "micro", "MALAYSIA")
        self.assertEqual(a, b)
        self.assertEqual(len(a), 12)

    def test_run_job_stages_and_diagnostics(self):
        def fetch(target):
            return (b'<?xml version="1.0"?><rss><channel>'
                    b'<item><title>Solar maintenance demand grows Malaysia</title>'
                    b'<link>https://example.org/a</link><pubDate>Mon, 26 Oct 2026 09:00:00 GMT</pubDate></item>'
                    b'</channel></rss>')

        def verify_fetch(target):
            return "<html><body>Solar maintenance demand grows Malaysia</body></html>"

        stages = []
        job, result, dossier = run_job("solar maintenance", capital="micro", fetch=fetch,
                                       verify_fetch=verify_fetch,
                                       on_stage=lambda s: stages.append(s), max_queries=1)
        self.assertEqual(job["status"], "completed")
        self.assertIn("diagnostics", job)
        self.assertGreaterEqual(job["diagnostics"]["candidates"], 1)
        self.assertEqual([s["name"] for s in job["stages"]][:3], ["researching", "verifying", "scoring"])
        self.assertEqual(stages[:3], ["researching", "verifying", "scoring"])
        self.assertEqual(dossier["top_candidate_id"], result["candidates"][0]["id"])
        line = diagnostics_line(job)
        self.assertIn("leads", line)

    def test_run_job_failure_recorded(self):
        def bad(target):
            raise OSError("boom")
        job, result, dossier = run_job("solar maintenance", fetch=bad, max_queries=1)
        # Per-subquery source failures are isolated: job completes, errors recorded.
        self.assertEqual(job["status"], "completed")
        self.assertEqual(result["candidates"], [])
        self.assertGreaterEqual(len(result["errors"]), 1)

    def test_is_duplicate_window(self):
        now = datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc)
        fresh = {"id": job_id("solar", "micro", "Malaysia"), "status": "completed",
                 "finished_at": now.isoformat()}
        stale = {"id": job_id("solar", "micro", "Malaysia"), "status": "completed",
                 "finished_at": datetime(2026, 10, 27, 9, 0, tzinfo=timezone.utc).isoformat()}
        self.assertIsNotNone(is_duplicate([fresh], "solar", "micro", now=now))
        self.assertIsNone(is_duplicate([stale], "solar", "micro", now=now))
        self.assertIsNone(is_duplicate([], "solar", "micro", now=now))

    def test_validate_topic_capital_and_errors(self):
        self.assertEqual(validate_topic("solar maintenance small"), ("solar maintenance", "small"))
        self.assertEqual(validate_topic("solar maintenance"), ("solar maintenance", "all"))
        self.assertEqual(validate_topic(""), (None, None))
        self.assertEqual(validate_topic("x" * 150), (None, None))
        self.assertEqual(validate_topic("solar huge"), ("solar huge", "all"))


if __name__ == "__main__":
    unittest.main()
