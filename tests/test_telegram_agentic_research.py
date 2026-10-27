"""Offline tests for the V2 Telegram research flow (fast ack → summary → report)."""
import unittest
from urllib.error import HTTPError
from pathlib import Path

import backend.telegram_poll_once as tp


def canned_result(query="aviation training Malaysia", capital="small"):
    return {
        "schema_version": 2,
        "generated_at": "2026-10-27T10:00:00+00:00",
        "plan": {"query": query, "country": "Malaysia", "capital": capital,
                 "sector": "aerospace", "rounds": []},
        "candidates": [
            {"id": "abc", "title": "Aviation training industry report",
             "source_url": "https://example.org/report", "published_at": None,
             "verification": {"verified": True, "retrieved_at": "x"},
             "score": {"total": 66, "metrics": {}, "weights": {}}},
        ],
        "errors": [],
        "gap_hits": {"competition": 0, "regulation": 1},
        "notice": "leads only",
    }


def canned_job(query, capital):
    return {"id": "abcdef123456", "query": query, "country": "Malaysia",
            "capital": capital, "status": "completed",
            "created_at": "2026-10-27T10:00:00+00:00",
            "finished_at": "2026-10-27T10:00:05+00:00", "duration_seconds": 5.0,
            "diagnostics": {"candidates": 1, "source_verified": 1, "source_errors": 0,
                            "gap_hits": {"competition": 0, "regulation": 1}, "top_score": 66,
                            "stages": [{"name": "researching", "seconds": 1.0}]}}


class ResearchTelegramTests(unittest.TestCase):
    def setUp(self):
        self._run_job = tp.run_job
        self._gen = tp.generate_report
        self._persist = tp.persist_jobs
        self._save = tp.save_job

    def tearDown(self):
        tp.run_job = self._run_job
        tp.generate_report = self._gen
        tp.persist_jobs = self._persist
        tp.save_job = self._save

    def _patch(self, query, capital):
        tp.run_job = lambda q, **k: (canned_job(q, capital), canned_result(q, capital), {})
        tp.generate_report = lambda dossier, result, out_dir: {"docx": str(out_dir / "report.docx"), "report": "r", "charts": [], "summary": {}}
        tp.persist_jobs = lambda repo, token, base=None: False
        tp.save_job = lambda job, result, paths: None

    def test_research_fast_ack_then_summary(self):
        self._patch("aviation training Malaysia", "small")
        calls = []
        outcome = tp.process_update(
            {"message": {"chat": {"id": 123}, "text": "/research aviation training Malaysia small"}},
            send=lambda method, payload: calls.append((method, payload)),
            allowed_ids="123", database=Path("missing.db"), ideas=[], token="tok")
        self.assertEqual(outcome, "sent")
        methods = [c[0] for c in calls]
        self.assertEqual(methods, ["sendMessage", "sendMessage"])
        ack, summary = calls[0][1]["text"], calls[1][1]["text"]
        self.assertIn("Research queued", ack)
        self.assertIn("360", summary)
        self.assertIn("Aviation training industry report", summary)
        self.assertIn("https://example.org/report", summary)
        self.assertIn("bc:report:abcdef123456", calls[1][1]["reply_markup"])

    def test_invalid_research_shows_usage_without_research(self):
        called = []
        tp.run_job = lambda *a, **k: called.append(1)
        calls = []
        tp.process_update({"message": {"chat": {"id": 123}, "text": "/research"}},
            send=lambda method, payload: calls.append((method, payload)),
            allowed_ids="123", database=Path("missing.db"), ideas=[], token="tok")
        self.assertEqual(called, [])
        self.assertIn("Usage:", calls[0][1]["text"])

    def test_expired_callback_does_not_block_ack(self):
        calls = []
        def send(method, payload):
            calls.append(method)
            if method == "answerCallbackQuery":
                raise HTTPError("https://example.org", 400, "expired", {}, None)
        outcome = tp.process_update(
            {"callback_query": {"id": "old", "data": "bc:home",
                                "message": {"chat": {"id": 123}, "message_id": 9}}},
            send=send, allowed_ids="123", database=Path("missing.db"), ideas=[])
        self.assertEqual(outcome, "sent")
        # The fast ack (answerCallbackQuery) comes first; a 400 (expired) is
        # swallowed and the menu edit still happens. No second answer.
        self.assertEqual(calls, ["answerCallbackQuery", "editMessageText"])

    def test_report_callback_missing_job_falls_back(self):
        calls = []
        def send(method, payload):
            calls.append((method, payload))
        outcome = tp.process_update(
            {"callback_query": {"id": "cb", "data": "bc:report:ffffffffffff",
                                "message": {"chat": {"id": 123}}}},
            send=send, allowed_ids="123", database=Path("missing.db"), ideas=[], token="tok")
        self.assertEqual(outcome, "sent")
        self.assertIn("not on this runner yet", calls[1][1]["text"])


if __name__ == "__main__":
    unittest.main()
