"""Offline tests for the BizCrax agent study & learning loop (fail-open, durable)."""
import json
import tempfile
import unittest
from pathlib import Path

import backend.agent_skill as agent


def make_result(n=5, verified=2, errors=0, titles=None):
    candidates = []
    for i in range(n):
        candidates.append({
            "title": (titles or ["solar install", "pv repair", "panel audit",
                                 "battery storage", "inverter service"])[i],
            "score": {"total": 80 - i * 3},
            "verification": {"verified": i < verified},
            "source_url": "https://example.com/%d" % i,
        })
    return {"plan": {"query": "solar", "country": "Malaysia", "capital": "small"},
            "candidates": candidates, "errors": ["err"] * errors,
            "gap_hits": {"competition": 1}}


class StudyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "state.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_study_earns_xp_and_saves_skill(self):
        out = agent.record_study("solar panel installation", "small", make_result(),
                                 new=True, path=self.path)
        self.assertEqual(out["xp_gain"], 40)  # 10 base + 5 effective + 25 new domain
        self.assertEqual(out["level"], 1)
        state = agent.load_state(self.path)
        self.assertEqual(state["studies"], 1)
        self.assertEqual(state["domains"]["energy"], 1)
        self.assertEqual(state["bands"]["small"], 1)
        self.assertEqual(len(state["skills"]), 1)
        self.assertIn("10 leads" if False else "leads", state["skills"][0]["lesson"])
        self.assertFalse(state["skills"][0]["ai"])

    def test_repeat_same_domain_is_worth_less(self):
        agent.record_study("solar panel installation", "small", make_result(),
                           new=True, path=self.path)
        out = agent.record_study("solar maintenance", "small", make_result(),
                                 new=True, path=self.path)
        self.assertEqual(out["xp_gain"], 15)  # 10 + 5 effective, no new-domain bonus
        self.assertFalse(out["new_domain"])

    def test_duplicate_research_is_worth_little(self):
        agent.record_study("solar panel installation", "small", make_result(),
                           new=True, path=self.path)
        out = agent.record_study("solar panel installation", "small", make_result(),
                                 new=False, path=self.path)
        self.assertEqual(out["xp_gain"], 2)

    def test_level_up_at_150_xp(self):
        # 140 XP, then a new-domain effective study (+40) crosses into level 2.
        state = {"version": 1, "xp": 140, "studies": 1,
                 "domains": {"food": 1}, "bands": {}, "skills": []}
        agent.save_state(state, self.path)
        out = agent.record_study("solar panels", "small", make_result(),
                                 new=True, path=self.path)
        self.assertEqual(out["xp"], 180)
        self.assertEqual(out["level"], 2)

    def test_domain_buckets(self):
        self.assertEqual(agent.domain_of("solar panel"), "energy")
        self.assertEqual(agent.domain_of("agritech cold chain"), "agri")
        self.assertEqual(agent.domain_of("cloud kitchen"), "food")
        self.assertEqual(agent.domain_of("saas billing"), "technology")
        self.assertEqual(agent.domain_of("quantum foobar"), "other")

    def test_ai_lesson_fail_open(self):
        def boom(settings, messages, max_tokens=120, timeout=20):
            raise OSError("minda down")
        original = agent.ai_bizcollector._chat
        agent.ai_bizcollector._chat = boom
        try:
            lesson = agent._ai_lesson("solar", "small", make_result())
            self.assertIsNone(lesson)
        finally:
            agent.ai_bizcollector._chat = original

    def test_ai_lesson_used_when_available(self):
        def fake_chat(settings, messages, max_tokens=120, timeout=20):
            return "  Solar queries work well; avoid news wrapper links.  "
        original = agent.ai_bizcollector._chat
        agent.ai_bizcollector._chat = fake_chat
        try:
            # explicit endpoint creds => env-independent (CI has no MINDA_* set)
            out = agent.record_study("solar panels", "small", make_result(),
                                     new=True, path=self.path, ai=True,
                                     base_url="http://minda.test", api_key="k",
                                     model="m")
            self.assertTrue(out["ai_lesson"])
            state = agent.load_state(self.path)
            self.assertEqual(state["skills"][0]["lesson"], "Solar queries work well; avoid news wrapper links.")
        finally:
            agent.ai_bizcollector._chat = original

    def test_state_text_lists_skills(self):
        agent.record_study("solar panels", "small", make_result(), new=True, path=self.path)
        text = agent.state_text(self.path)
        self.assertIn("Level 1", text)
        self.assertIn("Domains studied", text)
        self.assertIn("energy", text)
        self.assertIn("Saved skills", text)
        self.assertIn("[v2]", text)

    def test_state_text_empty(self):
        text = agent.state_text(self.path)
        self.assertIn("No skills yet", text)

    def test_skills_capped(self):
        state = agent._default_state()
        for i in range(agent.MAX_SKILLS + 5):
            state["skills"].append({"lesson": "s%d" % i})
        agent.save_state(state, self.path)
        agent.record_study("solar", "small", make_result(), new=True, path=self.path)
        state = agent.load_state(self.path)
        self.assertLessEqual(len(state["skills"]), agent.MAX_SKILLS)

    def test_corrupt_state_fail_open(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("{not json", encoding="utf-8")
        out = agent.record_study("solar", "small", make_result(), new=True, path=self.path)
        self.assertGreater(out["xp_gain"], 0)  # fresh state used
        self.assertEqual(agent.load_state(self.path)["studies"], 1)

    def test_study_menu_json(self):
        data = json.loads(agent.study_menu())
        self.assertIn("bc:research", json.dumps(data))


if __name__ == "__main__":
    unittest.main()
