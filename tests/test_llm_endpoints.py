"""Offline tests for llm_endpoints failover chain + ai_bizcollector._chat_failover."""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import llm_endpoints
from backend import ai_bizcollector


def clear_env():
    for k in ("MINDA_BASE_URL", "MINDA_API_KEY", "MINDA_MODEL",
              "LLM_PROXY_BASE_URL", "LLM_PROXY_API_KEY", "LLM_PROXY_MODEL"):
        os.environ.pop(k, None)


class ChainTest(unittest.TestCase):
    def setUp(self):
        clear_env()

    def test_empty_when_nothing_set(self):
        self.assertEqual(llm_endpoints.chain(), [])
        self.assertIsNone(llm_endpoints.first())

    def test_minda_only(self):
        os.environ["MINDA_BASE_URL"] = "http://minda:8080/"
        os.environ["MINDA_API_KEY"] = "k1"
        self.assertEqual(llm_endpoints.chain(), [("http://minda:8080", "k1", "llm_model_fp8")])

    def test_minda_then_proxy_order(self):
        os.environ["MINDA_BASE_URL"] = "http://minda:8080"
        os.environ["MINDA_API_KEY"] = "k1"
        os.environ["LLM_PROXY_BASE_URL"] = "http://proxy:8317/v1"
        os.environ["LLM_PROXY_API_KEY"] = "k2"
        os.environ["LLM_PROXY_MODEL"] = "claude-sonnet"
        c = llm_endpoints.chain()
        self.assertEqual(len(c), 2)
        self.assertEqual(c[0][0], "http://minda:8080")
        self.assertEqual(c[1], ("http://proxy:8317/v1", "k2", "claude-sonnet"))

    def test_proxy_only(self):
        os.environ["LLM_PROXY_BASE_URL"] = "http://proxy:8317"
        os.environ["LLM_PROXY_API_KEY"] = "k2"
        c = llm_endpoints.chain()
        self.assertEqual(len(c), 1)
        self.assertEqual(c[0][0], "http://proxy:8317")

    def test_first_returns_primary(self):
        os.environ["MINDA_BASE_URL"] = "http://minda"
        os.environ["MINDA_API_KEY"] = "k1"
        self.assertEqual(llm_endpoints.first(), ("http://minda", "k1", "llm_model_fp8"))

    def test_describe_redacts_keys(self):
        os.environ["MINDA_BASE_URL"] = "http://minda"
        os.environ["MINDA_API_KEY"] = "secretkey123"
        d = llm_endpoints.describe()
        self.assertIn("primary", d)
        self.assertNotIn("secretkey123", d)


class ChatFailoverTest(unittest.TestCase):
    def test_first_success(self):
        with mock.patch.object(ai_bizcollector, "_chat", side_effect=["ok"]) as ch:
            self.assertEqual(ai_bizcollector._chat_failover([("a", "1", "m"), ("b", "2", "m")],
                                                            [{"role": "user", "content": "x"}]), "ok")
            self.assertEqual(ch.call_count, 1)

    def test_falls_to_second_on_error(self):
        side = [OSError("minda down"), "fallback-ok"]
        with mock.patch.object(ai_bizcollector, "_chat", side_effect=side) as ch:
            self.assertEqual(ai_bizcollector._chat_failover([("a", "1", "m"), ("b", "2", "m")],
                                                            [{"role": "user", "content": "x"}]), "fallback-ok")
            self.assertEqual(ch.call_count, 2)

    def test_none_when_all_fail(self):
        with mock.patch.object(ai_bizcollector, "_chat", side_effect=OSError("down")):
            self.assertIsNone(ai_bizcollector._chat_failover([("a", "1", "m"), ("b", "2", "m")],
                                                             [{"role": "user", "content": "x"}]))

    def test_explicit_endpoint_bypasses_chain(self):
        clear_env()
        eps = ai_bizcollector._endpoints(base_url="http://x", api_key="k", model="m")
        self.assertEqual(eps, [("http://x", "k", "m")])
        clear_env()
        self.assertEqual(ai_bizcollector._endpoints(), [])


class IntentFailoverTest(unittest.TestCase):
    def test_intent_uses_failover_chain(self):
        clear_env()
        os.environ["MINDA_BASE_URL"] = "http://minda"
        os.environ["MINDA_API_KEY"] = "k1"
        os.environ["LLM_PROXY_BASE_URL"] = "http://proxy"
        os.environ["LLM_PROXY_API_KEY"] = "k2"
        raw = json.dumps({"intent": "research", "topic": "solar maintenance", "capital": "small"})
        with mock.patch.object(ai_bizcollector, "_chat", side_effect=[OSError("down"), raw]):
            out = ai_bizcollector.ask_intent("find solar maintenance business")
        self.assertEqual(out, {"intent": "research", "topic": "solar maintenance", "capital": "small"})
        clear_env()


if __name__ == "__main__":
    unittest.main()
