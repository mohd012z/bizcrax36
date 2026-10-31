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

    def test_csv_duplicate_header_rejected_before_silent_overwrite(self):
        data = (b"id,title,title,source_url,status\\n"
                b"lead_1,Original,Overwritten,https://example.org,review_required\\n")
        with self.assertRaisesRegex(ValueError, "duplicates"):
            import_data(data.replace(b"\\n", b"\n"), ".csv")

    def test_csv_extra_column_value_rejected(self):
        data = (b"id,title,source_url,status\n"
                b"lead_1,Example,https://example.org,review_required,unexpected\n")
        with self.assertRaisesRegex(ValueError, "missing or extra"):
            import_data(data, ".csv")

    def test_csv_missing_column_value_rejected(self):
        data = (b"id,title,source_url,status\n"
                b"lead_1,Example,https://example.org\n")
        with self.assertRaisesRegex(ValueError, "missing or extra"):
            import_data(data, ".csv")



    def test_atomic_claim_deduplicates_across_connections(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "updates.sqlite3"
            first, second = UpdateLedger(path), UpdateLedger(path)
            try:
                self.assertTrue(first.claim(700))
                self.assertFalse(second.claim(700))
                self.assertTrue(second.claim(701))
                self.assertFalse(first.claim(701))
            finally:
                first.close()
                second.close()

    def test_atomic_claim_persists_after_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "updates.sqlite3"
            first = UpdateLedger(path)
            self.assertTrue(first.claim(702))
            first.close()
            second = UpdateLedger(path)
            try:
                self.assertFalse(second.claim(702))
            finally:
                second.close()

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
