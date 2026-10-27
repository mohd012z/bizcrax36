import unittest
from urllib.error import HTTPError
from pathlib import Path
from backend.telegram_poll_once import process_update

class ResearchTelegramTests(unittest.TestCase):
    def test_research_command_delivers_candidates(self):
        calls=[]
        def fake(query, max_queries):
            self.assertEqual(query, "aviation training Malaysia")
            self.assertEqual(max_queries, 3)
            return {"plan":{"query":query},"errors":[],"candidates":[
                {"title":"Aviation training industry report","source_url":"https://example.org/report"}]}
        outcome=process_update({"message":{"chat":{"id":123},"text":"/research aviation training Malaysia"}},
            send=lambda method,payload:calls.append((method,payload)),allowed_ids="123",
            database=Path("missing.db"),ideas=[],researcher=fake)
        self.assertEqual(outcome,"sent")
        self.assertIn("REVIEW_REQUIRED",calls[0][1]["text"])
        self.assertIn("https://example.org/report",calls[0][1]["text"])

    def test_invalid_research_does_not_call_provider(self):
        calls=[]
        process_update({"message":{"chat":{"id":123},"text":"/research"}},
            send=lambda method,payload:calls.append((method,payload)),allowed_ids="123",
            database=Path("missing.db"),ideas=[],researcher=lambda *a,**k:self.fail("called"))
        self.assertIn("Usage:",calls[0][1]["text"])

    def test_expired_callback_does_not_block_ack(self):
        calls=[]
        def send(method,payload):
            calls.append(method)
            if method=="answerCallbackQuery":
                raise HTTPError("https://example.org",400,"expired",{},None)
        outcome=process_update({"callback_query":{"id":"old","data":"bc:home",
            "message":{"chat":{"id":123},"message_id":9}}},
            send=send,allowed_ids="123",database=Path("missing.db"),ideas=[])
        self.assertEqual(outcome,"sent")
        self.assertEqual(calls,["editMessageText","answerCallbackQuery"])

if __name__=="__main__":
    unittest.main()
