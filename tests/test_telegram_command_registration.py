import unittest
from unittest.mock import patch
from scripts.register_telegram_commands import COMMANDS, register


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, *args):
        return b'{"ok":true,"result":true}'


class CommandRegistrationTests(unittest.TestCase):
    def test_expected_commands(self):
        self.assertEqual([item["command"] for item in COMMANDS],
                         ["start", "research", "status", "sector", "help"])

    def test_missing_token_fails(self):
        with self.assertRaises(ValueError):
            register("")

    def test_registration_request(self):
        captured = {}

        def opener(req, timeout):
            captured["url"] = req.full_url
            captured["body"] = req.data
            return FakeResponse()

        self.assertTrue(register("test-token", opener))
        self.assertTrue(captured["url"].endswith("/setMyCommands"))
        self.assertIn(b'"research"', captured["body"])


if __name__ == "__main__":
    unittest.main()
