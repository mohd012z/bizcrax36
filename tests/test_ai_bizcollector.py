"""Offline tests for the AI bizcollector layer (Minda intent + synthesis, fail-open)."""
import json
import unittest
from urllib.error import HTTPError

import backend.ai_bizcollector as ai


def fake_chat(settings, messages, max_tokens=300, timeout=60):
    content = messages[-1]["content"]
    if "intent parser" in content:
        if "food" in content:
            return '{"intent": "research", "topic": "food processing", "capital": "micro"}'
        return '{"intent": "research", "topic": "solar maintenance", "capital": "small"}'
    return ("[FACT] Candidate leads mention solar demand in Malaysia. "
            "[INFER] SME service model fits the small band. "
            "[ASSUME] Competitor pricing is moderate. Verify: fetch the top issuer notice first.")


SETTINGS = ("https://minda.example/v1", "key-never-printed", "llm_model_fp8")


class IntentTests(unittest.TestCase):
    def _with_fake(self, fn, *a, **k):
        original = ai._chat
        ai._chat = fake_chat
        try:
            return fn(*a, **k)
        finally:
            ai._chat = original

    def test_research_intent(self):
        intent = self._with_fake(
            lambda: ai.ask_intent("find a low cost food business",
                                  base_url="https://minda.example/v1", api_key="k", model="m"))
        self.assertEqual(intent["intent"], "research")
        self.assertEqual(intent["topic"], "food processing")
        self.assertEqual(intent["capital"], "micro")

    def test_capital_default_all(self):
        intent = self._with_fake(
            lambda: ai.ask_intent("research solar maintenance",
                                  base_url="https://minda.example/v1", api_key="k", model="m"))
        self.assertEqual(intent["capital"], "small")  # fake returns small for solar

    def test_no_settings_returns_none(self):
        self.assertIsNone(ai.ask_intent("hello", base_url=None, api_key="k"))
        self.assertIsNone(ai.ask_intent("hello", base_url="https://x", api_key=None))
        self.assertIsNone(ai.ask_intent("", base_url="https://x", api_key="k"))

    def test_llm_down_fail_open(self):
        def boom(*a, **k):
            raise HTTPError("https://minda.example", 503, "gateway", {}, None)
        original = ai._chat
        ai._chat = boom
        try:
            self.assertIsNone(ai.ask_intent("solar", base_url="https://x", api_key="k", model="m"))
            self.assertIsNone(ai.synthesize("solar", {"candidates": [{"title": "t", "score": {"total": 1}}]},
                                            base_url="https://x", api_key="k", model="m"))
        finally:
            ai._chat = original

    def test_malformed_json_fail_open(self):
        original = ai._chat
        ai._chat = lambda *a, **k: "not json at all"
        try:
            self.assertIsNone(ai.ask_intent("solar", base_url="https://x", api_key="k", model="m"))
        finally:
            ai._chat = original

    def test_synthesize_labels_and_cap(self):
        result = {"plan": {"query": "solar maintenance", "country": "Malaysia", "capital": "small"},
                  "errors": [], "gap_hits": {"competition": 1},
                  "candidates": [{"title": "Solar demand grows in Malaysia", "score": {"total": 60},
                                  "verification": {"verified": True}, "source_url": "https://e.org/a"}]}
        text = self._with_fake(
            lambda: ai.synthesize("solar maintenance", result,
                                  base_url="https://minda.example/v1", api_key="k", model="m"))
        self.assertIn("[FACT]", text)
        self.assertIn("[INFER]", text)
        self.assertLessEqual(len(text), 900)

    def test_synthesize_empty_candidates(self):
        self.assertIsNone(ai.synthesize("solar", {"candidates": []},
                                        base_url="https://minda.example/v1", api_key="k", model="m"))


class TelegramAiFlowTests(unittest.TestCase):
    """Menu + callback + /ai wiring, offline (monkeypatched research/AI)."""

    def setUp(self):
        import backend.telegram_poll_once as tp
        self.tp = tp
        self._run_job = tp.run_job
        self._gen = tp.generate_report
        self._persist = tp.persist_jobs
        self._save = tp.save_job
        self._ask = tp.ai_bizcollector.ask_intent
        self._synth = tp.ai_bizcollector.synthesize

    def tearDown(self):
        tp = self.tp
        tp.run_job = self._run_job
        tp.generate_report = self._gen
        tp.persist_jobs = self._persist
        tp.save_job = self._save
        tp.ai_bizcollector.ask_intent = self._ask
        tp.ai_bizcollector.synthesize = self._synth

    def _canned(self, query="solar maintenance", capital="small"):
        return {"id": "abcdef123456", "query": query, "country": "Malaysia",
                "capital": capital, "status": "completed",
                "created_at": "2026-10-27T10:00:00+00:00",
                "finished_at": "2026-10-27T10:00:05+00:00",
                "diagnostics": {"candidates": 1, "source_verified": 1, "source_errors": 0,
                                "gap_hits": {}, "top_score": 60, "duration_seconds": 5.0,
                                "stages": [{"name": "researching", "seconds": 1.0}]}}

    def _patch(self):
        tp = self.tp
        def fake_run_job(q, **k):
            result = {"schema_version": 2,
                      "generated_at": "2026-10-27T10:00:05+00:00",
                      "plan": {"query": q, "country": "Malaysia", "capital": k.get("capital", "all"),
                               "sector": "general", "rounds": []},
                      "candidates": [{"id": "a", "title": "Solar demand grows",
                                      "source_url": "https://e.org/a", "verification": {"verified": True},
                                      "score": {"total": 60, "metrics": {}, "weights": {}}}],
                      "errors": [], "gap_hits": {}, "notice": "leads"}
            return self._canned(q, k.get("capital", "all")), result, {}
        tp.run_job = fake_run_job
        tp.generate_report = lambda d, r, out: {"docx": "x", "report": "r", "charts": [], "summary": {}}
        tp.persist_jobs = lambda *a, **k: False
        tp.save_job = lambda *a, **k: None

    def test_ai_menu_shows_shortcuts(self):
        menu = json.loads(self.tp.ai_menu())
        data = [btn["callback_data"] for row in menu["inline_keyboard"] for btn in row]
        self.assertIn("bc:ai:hot", data)
        self.assertIn("bc:ai:low", data)
        self.assertIn("bc:ai:ask", data)

    def test_home_has_ai_button(self):
        import json as j
        home = j.loads(self.tp.home())
        data = [b["callback_data"] for row in home["inline_keyboard"] for b in row]
        self.assertIn("bc:aimenu", data)

    def test_ai_command_flow_with_synthesis(self):
        tp = self.tp
        self._patch()
        tp.ai_bizcollector.ask_intent = lambda text, **k: {"intent": "research",
                                                           "topic": "solar maintenance", "capital": "small"}
        tp.ai_bizcollector.synthesize = lambda q, r, **k: "[FACT] demand up. Verify issuer."
        calls = []
        outcome = tp.process_update(
            {"message": {"chat": {"id": 1}, "text": "/ai find solar business low cost"}},
            send=lambda m, p: calls.append((m, p)), allowed_ids="1",
            database=None, ideas=[], token="tok")
        self.assertEqual(outcome, "sent")
        # ack + summary (2 sendMessage)
        summaries = [p["text"] for m, p in calls if m == "sendMessage"]
        self.assertTrue(any("AI SYNTHESIS" in s and "[FACT]" in s for s in summaries))
        self.assertTrue(any("Research queued" in s for s in summaries))

    def test_ai_command_fail_open_without_minda(self):
        tp = self.tp
        self._patch()
        tp.ai_bizcollector.ask_intent = lambda text, **k: None
        tp.ai_bizcollector.synthesize = lambda q, r, **k: None
        calls = []
        outcome = tp.process_update(
            {"message": {"chat": {"id": 1}, "text": "/ai solar maintenance small"}},
            send=lambda m, p: calls.append((m, p)), allowed_ids="1",
            database=None, ideas=[], token="tok")
        self.assertEqual(outcome, "sent")
        summaries = [p["text"] for m, p in calls if m == "sendMessage"]
        self.assertFalse(any("AI SYNTHESIS" in s for s in summaries))
        self.assertTrue(any("360" in s for s in summaries))

    def test_ai_shortcut_callback_runs_research(self):
        tp = self.tp
        self._patch()
        tp.ai_bizcollector.ask_intent = lambda text, **k: {"intent": "research",
                                                           "topic": text, "capital": "all"}
        tp.ai_bizcollector.synthesize = lambda q, r, **k: None
        calls = []
        outcome = tp.process_update(
            {"callback_query": {"id": "cb", "data": "bc:ai:hot",
                                "message": {"chat": {"id": 1}}}},
            send=lambda m, p: calls.append((m, p)), allowed_ids="1",
            database=None, ideas=[], token="tok")
        self.assertEqual(outcome, "sent")
        acks = [p["text"] for m, p in calls if m == "sendMessage"]
        self.assertTrue(any("Research queued" in a for a in acks))

    def test_ai_menu_callback(self):
        tp = self.tp
        tp.ai_bizcollector.ask_intent = lambda text, **k: None
        calls = []
        outcome = tp.process_update(
            {"callback_query": {"id": "cb", "data": "bc:aimenu",
                                "message": {"chat": {"id": 1}}}},
            send=lambda m, p: calls.append((m, p)), allowed_ids="1",
            database=None, ideas=[], token="tok")
        self.assertEqual(outcome, "sent")
        self.assertIn("bc:ai:hot", calls[0][1]["reply_markup"])


if __name__ == "__main__":
    unittest.main()
