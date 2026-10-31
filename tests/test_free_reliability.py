import tempfile
import unittest
from pathlib import Path
from backend.free_reliability import (
    UpdateLedger, command_payload, export_data, import_data, parse_command, validate_rows
)

ROWS = [{"id": "lead_1", "title": "SME document automation",
         "source_url": "https://example.org/source", "status": "research_hypothesis"}]

class FreeReliabilityTests(unittest.TestCase):
    def test_command_registration(self):
        commands = command_payload()
        self.assertEqual(len(commands), len({x["command"] for x in commands}))
        self.assertEqual(parse_command("/research@bizcollectorbot SME OCR"), ("research", "SME OCR"))

    def test_json_roundtrip(self):
        self.assertEqual(import_data(export_data(ROWS, ".json"), ".json"), ROWS)

    def test_csv_roundtrip(self):
        self.assertEqual(import_data(export_data(ROWS, ".csv"), ".csv"), ROWS)

    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            validate_rows(ROWS + ROWS)

    def test_ledger_survives_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "updates.sqlite3"
            a = UpdateLedger(path)
            a.mark(123)
            a.close()
            b = UpdateLedger(path)
            self.assertTrue(b.seen(123))
            self.assertFalse(b.seen(124))
            b.close()

if __name__ == "__main__":
    unittest.main()
