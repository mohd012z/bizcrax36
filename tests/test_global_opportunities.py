import unittest
from backend.global_opportunities import assess, SOURCES, value_class
class GlobalOpportunitiesTests(unittest.TestCase):
    def test_any_value_including_zero(self):
        self.assertEqual(value_class(0),"disclosed")
        self.assertEqual(value_class("0.01"),"disclosed")
        self.assertEqual(value_class("100000000000"),"disclosed")
    def test_undisclosed_value(self):
        self.assertEqual(value_class(None),"undisclosed")
        self.assertEqual(value_class(""),"undisclosed")
    def test_invalid_value(self):
        self.assertEqual(value_class("-1"),"invalid")
        self.assertEqual(value_class("nan"),"invalid")
    def test_foreign_eligibility_needs_review(self):
        result=assess({"title":"Example","type":"partnership","country":"Singapore",
                       "contract_value":None})
        self.assertEqual(result["shortlist_status"],"review_required")
        self.assertTrue(result["entry_barriers"])
    def test_official_registry_exists(self):
        self.assertGreaterEqual(len(SOURCES),5)
if __name__=="__main__":unittest.main()
