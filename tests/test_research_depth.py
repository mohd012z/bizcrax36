import unittest
from backend.research_depth import completeness, sensitivity
class ResearchDepthTests(unittest.TestCase):
    def test_empty_research_is_incomplete(self):
        r=completeness({})
        self.assertFalse(r["all_fields_complete"])
        self.assertEqual(r["domains"]["market"]["completeness_percent"],0)
    def test_partial_research(self):
        r=completeness({"market":{"market_size":"RM estimate","geography":"Malaysia"}})
        self.assertIn("market_growth",r["domains"]["market"]["missing"])
        self.assertEqual(r["domains"]["market"]["completeness_percent"],40)
    def test_scenarios(self):
        r=sensitivity({"startup_cost":2000,"price_per_sale":500,"variable_cost_per_sale":150,
            "monthly_fixed_cost":1000,"sales_per_month":5,"cash_available":2500})
        self.assertEqual([x["sales_per_month"] for x in r["scenarios"]],[2,5,7])
        self.assertEqual(r["scenarios"][1]["monthly_operating_profit"],"750")
    def test_incomplete_finances(self):
        self.assertEqual(sensitivity({})["status"],"insufficient_inputs")
if __name__=="__main__":unittest.main()
