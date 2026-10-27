"""Offline tests for report generation: PNG charts and strict-OOXML DOCX."""
import struct
import unittest
import zipfile
from xml.etree import ElementTree

from backend.dossier import build as build_dossier
from backend.reports import (generate_report, render_score_chart, render_metric_chart,
                             render_scenario_chart, scenario_series, write_png)


def result_fixture():
    return {
        "schema_version": 2,
        "generated_at": "2026-10-27T10:00:00+00:00",
        "plan": {"query": "solar maintenance", "country": "Malaysia", "capital": "micro",
                 "sector": "energy", "rounds": []},
        "candidates": [
            {"id": "a1", "title": "Solar panel maintenance demand surges in Malaysia",
             "source_url": "https://example.org/solar",
             "verification": {"verified": True},
             "score": {"total": 71, "metrics": {
                 "demand": {"value": 80, "basis": "evidence", "note": "n"},
                 "unit_economics": {"value": 40, "basis": "assumed", "note": "n"},
                 "competition": {"value": 75, "basis": "evidence", "note": "n"},
                 "capital_accessibility": {"value": 85, "basis": "assumed", "note": "n"},
                 "operational_feasibility": {"value": 50, "basis": "assumed", "note": "n"},
                 "regulatory_readiness": {"value": 80, "basis": "evidence", "note": "n"}},
                 "weights": {"demand": 25, "unit_economics": 15, "competition": 15,
                             "capital_accessibility": 15, "operational_feasibility": 15,
                             "regulatory_readiness": 15}}},
            {"id": "a2", "title": "Tender: solar farm maintenance services",
             "source_url": "https://example.org/tender",
             "verification": {"verified": False},
             "score": {"total": 55, "metrics": {}, "weights": {}}},
        ],
        "errors": [],
        "gap_hits": {"competition": 1, "regulation": 1},
        "notice": "leads only",
    }


FINANCIALS = {"startup_cost": 50000, "price_per_sale": 1000, "variable_cost_per_sale": 400,
              "monthly_fixed_cost": 15000, "sales_per_month": 50, "cash_available": 40000}


def _png_ok(data, width, height):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return False, "bad signature"
    if data[8:12] != struct.pack(">I", 13):
        return False, "missing IHDR"
    w, h = struct.unpack(">II", data[16:24])
    if (w, h) != (width, height):
        return False, "dims %dx%d" % (w, h)
    return True, "ok"


class PngTests(unittest.TestCase):
    def test_write_png_signature_and_dims(self):
        data = write_png(4, 2, [b"\xff" * 12, b"\x00" * 12])
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
        ok, why = _png_ok(data, 4, 2)
        self.assertTrue(ok, why)

    def test_score_chart_renders(self):
        out = render_score_chart(result_fixture()["candidates"], "/tmp/bc36_scores.png", max_items=2)
        data = open(out, "rb").read()
        ok, why = _png_ok(data, 640, 90 + 2 * 44)
        self.assertTrue(ok, why)
        self.assertGreater(len(data), 100)

    def test_metric_chart_renders(self):
        out = render_metric_chart(result_fixture()["candidates"][0], "/tmp/bc36_metrics.png")
        data = open(out, "rb").read()
        ok, why = _png_ok(data, 640, 90 + 6 * 40)
        self.assertTrue(ok, why)

    def test_scenario_chart_renders(self):
        series = scenario_series(FINANCIALS)
        self.assertIsNotNone(series)
        self.assertEqual(len(series), 3)
        out = render_scenario_chart(series, "/tmp/bc36_scenarios.png")
        data = open(out, "rb").read()
        ok, why = _png_ok(data, 640, 400)
        self.assertTrue(ok, why)

    def test_scenario_series_none_when_inputs_missing(self):
        self.assertIsNone(scenario_series({"startup_cost": 1}))


class DocxTests(unittest.TestCase):
    def test_generate_report_produces_valid_docx(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            out = generate_report(build_dossier(result_fixture()), result_fixture(),
                                  tmp, financials=FINANCIALS)
            docx = out["docx"]
            self.assertTrue(Path(docx).exists())
            self.assertEqual(len(out["charts"]), 3)
            with zipfile.ZipFile(docx) as zf:
                names = zf.namelist()
                self.assertIn("[Content_Types].xml", names)
                self.assertIn("word/document.xml", names)
                self.assertIn("word/styles.xml", names)
                self.assertIn("word/_rels/document.xml.rels", names)
                self.assertIn("word/media/scores.png", names)
                self.assertIn("word/media/metrics.png", names)
                self.assertIn("word/media/scenarios.png", names)
                document = zf.read("word/document.xml").decode("utf-8")
                # strict OOXML: parseable, correct root namespace
                root = ElementTree.fromstring(document)
                self.assertEqual(
                    root.tag, "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}document")
                for section_title in ("EXECUTIVE SUMMARY", "FINANCIAL FORECAST",
                                      "FUNDING AND INVESTMENT", "SOURCE VERIFICATION"):
                    self.assertIn(section_title, document.upper().replace("—", " "))
                self.assertIn("ASSUMED", document)
                self.assertIn("EVIDENCE", document.upper())
                rels = zf.read("word/_rels/document.xml.rels").decode("utf-8")
                self.assertEqual(rels.count("relationships/image"), 3)
                # every image referenced in document must have a rel
                for rid in ("rId2", "rId3", "rId4"):
                    self.assertIn('Id="%s"' % rid, rels)
                # no raw & outside escaped entities (would break XML — fromstring above already proves it)

    def test_generate_report_without_financials(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            out = generate_report(build_dossier(result_fixture()), result_fixture(), tmp)
            self.assertEqual(len(out["charts"]), 2)  # scores + metrics only
            with zipfile.ZipFile(out["docx"]) as zf:
                self.assertIn("word/media/scores.png", zf.namelist())
                self.assertNotIn("word/media/scenarios.png", zf.namelist())


if __name__ == "__main__":
    unittest.main()
