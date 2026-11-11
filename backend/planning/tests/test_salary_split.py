from decimal import Decimal

from config.testing import ApiTestCase

URL = "/api/plan/tools/salary-split"


class SalarySplitTests(ApiTestCase):
    def test_the_advance_is_a_part_of_the_gross_and_the_rest_is_the_net_pay_less_it(self):
        payload = {"gross": "5000.00", "advance_percent": "40"}
        body = self.post(URL, payload).json()
        salary = self.post("/api/plan/tools/salary", {"gross": "5000.00"}).json()
        net = salary["month"]["net"]
        self.assertEqual(body["advance"], "2000.00")
        self.assertEqual(body["net"], net)
        self.assertEqual(Decimal(body["remainder"]), Decimal(net) - Decimal("2000.00"))
        self.assertEqual((body["year"], body["assumed"]), (salary["year"], salary["assumed"]))
        self.assertEqual(
            (body["inss"], body["irrf"]), (salary["month"]["inss"], salary["month"]["irrf"])
        )

    def test_the_deductions_lower_the_rest(self):
        plain = self.post(URL, {"gross": "5000.00", "advance_percent": "40"}).json()
        body = self.post(
            URL, {"gross": "5000.00", "advance_percent": "40", "other": "100.00"}
        ).json()
        self.assertEqual(body["advance"], plain["advance"])
        self.assertEqual(Decimal(body["remainder"]), Decimal(plain["remainder"]) - 100)

    def test_an_advance_that_takes_the_whole_net_pay_is_refused(self):
        response = self.post(URL, {"gross": "5000.00", "advance_percent": "95"})
        self.assert_errors(response, 400, "advance_percent")

    def test_the_calculation_needs_a_session(self):
        self.client.logout()
        self.assertEqual(
            self.post(URL, {"gross": "5000.00", "advance_percent": "40"}).status_code, 401
        )
