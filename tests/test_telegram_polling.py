import unittest
from unittest.mock import patch
from hosting import telegram_polling as bot


class PollingTests(unittest.TestCase):
    def setUp(self):
        self.old_allowed = bot.ALLOWED
        bot.ALLOWED = {"123"}

    def tearDown(self):
        bot.ALLOWED = self.old_allowed

    @patch.object(bot, "send")
    def test_status(self, send):
        bot.process({"update_id": 1, "message": {"chat": {"id": 123}, "text": "/status"}})
        send.assert_called_once()
        self.assertIn("online", send.call_args.args[1])

    @patch.object(bot, "send")
    def test_unauthorized_chat_ignored(self, send):
        bot.process({"update_id": 2, "message": {"chat": {"id": 999}, "text": "/status"}})
        send.assert_not_called()

    @patch.object(bot, "dispatch")
    @patch.object(bot, "send")
    def test_research_dispatch(self, send, dispatch):
        bot.process({"update_id": 42, "message": {"chat": {"id": 123}, "text": "/research aviation Malaysia"}})
        dispatch.assert_called_once_with("aviation Malaysia", 123, "tg-42")
        self.assertIn("tg-42", send.call_args.args[1])

    @patch.object(bot, "dispatch")
    @patch.object(bot, "send")
    def test_empty_research_rejected(self, send, dispatch):
        bot.process({"update_id": 3, "message": {"chat": {"id": 123}, "text": "/research"}})
        dispatch.assert_not_called()
        self.assertIn("Usage", send.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
