import unittest
from backend.business_blueprint import build_plan, financial_model

class BlueprintTests(unittest.TestCase):
    def test_missing_information_never_launch_ready(self):
        report=build_plan({"id":"sample","name":"Example","horizon":"short"})
        self.assertFalse(report["ready_to_launch"])
        self.assertIn("target_customers",report["missing_inputs"])
    def test_break_even(self):
        m=financial_model({"startup_cost":1000,"price_per_sale":100,
          "variable_cost_per_sale":40,"monthly_fixed_cost":600,
          "sales_per_month":20,"cash_available":1500})
        self.assertEqual(m["break_even_sales_per_month"],10)
        self.assertEqual(m["monthly_operating_profit"],"600")
        self.assertEqual(m["cash_after_startup"],"500")
    def test_no_negative_cost(self):
        with self.assertRaises(ValueError):
            financial_model({"startup_cost":-1,"price_per_sale":10,"variable_cost_per_sale":5,
                "monthly_fixed_cost":2,"sales_per_month":1,"cash_available":10})
    def test_no_fake_validation(self):
        report=build_plan({"id":"demo","name":"Pilot","horizon":"long","evidence":[
            {"claim":"Demand exists","source_url":"https://example.org","retrieved_at":"2026-10-27","source_type":"customer_interview"}]})
        self.assertEqual(report["evidence_count"],1)
        self.assertFalse(report["gates"]["customer_validation"])
        self.assertFalse(report["gates"]["commercially_validated"])
if __name__=="__main__":unittest.main()
