from datetime import date
from decimal import Decimal

from ledger.models import TransactionSplit
from reports.tests.test_api import ReportsApiTestCase

URL = "/api/reports/analysis"


class AnalysisTestCase(ReportsApiTestCase):
    """Today is 2026-11-10. The base records cover three months and two categories."""

    def analysis(self, **query):
        response = self.get(URL, **query)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def flow(self, **query):
        flows = self.analysis(**query)["flows"]
        self.assertEqual(len(flows), 1, flows)
        return flows[0]

    def records(self):
        self.record(
            title="Salário", amount="5000.00", transaction_type="INCOME", category_id=self.salary.pk
        )
        self.record(amount="120.50")
        self.record(title="Cinema", amount="60.00", category_id=self.fun.pk)
        self.record(title="Outubro", amount="40.00", date="2026-10-05")
        self.record(title="Agosto", amount="70.00", date="2026-08-10")

    def invest(self, **changes):
        payload = {
            "name": "Reserva",
            "institution_id": self.account.bank_id,
            "currency": "BRL",
            "opening_balance": "2000.00",
            "opening_date": "2026-09-15",
            **changes,
        }
        response = self.post("/api/investments/positions", payload)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["id"]


class PeriodTests(AnalysisTestCase):
    def period(self, **query):
        body = self.analysis(**query)
        return body["start"], body["end"], len(body["months"])

    def test_without_a_period_the_analysis_has_the_six_months_to_the_current_one(self):
        self.assertEqual(self.period(), ("2026-06-01", "2026-11-01", 6))
        self.assertEqual(self.period(start="nonsense", end="2026-13"), self.period())

    def test_a_given_period_is_kept_and_its_months_are_in_order(self):
        body = self.analysis(start="2026-09", end="2026-10")
        self.assertEqual(body["months"], ["2026-09-01", "2026-10-01"])
        # The period before it has the same length and ends where this one starts.
        self.assertEqual(body["previous_start"], "2026-07-01")

    def test_a_period_ends_at_the_current_month_and_starts_before_its_end(self):
        self.assertEqual(
            self.period(start="2026-10", end="2027-03"), ("2026-10-01", "2026-11-01", 2)
        )
        self.assertEqual(
            self.period(start="2026-11", end="2026-09"), ("2026-09-01", "2026-09-01", 1)
        )

    def test_a_period_has_at_most_sixty_months(self):
        self.assertEqual(
            self.period(start="2015-01", end="2026-11"), ("2021-12-01", "2026-11-01", 60)
        )

    def test_a_period_is_comparable_when_the_period_before_is_inside_the_records(self):
        self.records()  # The oldest record is of August.
        self.assertTrue(self.analysis(start="2026-10", end="2026-11")["comparable"])
        self.assertTrue(self.analysis(start="2026-09", end="2026-09")["comparable"])
        # The period before starts in July or earlier: its totals would be too small.
        self.assertFalse(self.analysis(start="2026-09", end="2026-11")["comparable"])
        self.assertFalse(self.analysis(start="2026-08", end="2026-08")["comparable"])

    def test_the_bounds_are_the_month_of_the_oldest_record_and_the_current_month(self):
        body = self.analysis()
        self.assertEqual((body["first"], body["last"]), ("2026-11-01", "2026-11-01"))
        self.records()
        self.invest(opening_date="2026-05-20")
        body = self.analysis()
        self.assertEqual((body["first"], body["last"]), ("2026-05-01", "2026-11-01"))


class FlowTests(AnalysisTestCase):
    def test_each_month_has_its_income_and_expenses_with_zeros(self):
        self.records()
        flow = self.flow(start="2026-09", end="2026-11")
        self.assertEqual(
            flow["months"],
            [
                {"month": "2026-09-01", "income": "0.00", "expenses": "0.00"},
                {"month": "2026-10-01", "income": "0.00", "expenses": "40.00"},
                {"month": "2026-11-01", "income": "5000.00", "expenses": "180.50"},
            ],
        )

    def test_the_totals_come_with_the_totals_of_the_period_before(self):
        self.records()
        flow = self.flow(start="2026-10", end="2026-11")
        self.assertEqual(
            {name: flow[name] for name in ("currency", "income", "expenses", "result")},
            {"currency": "BRL", "income": "5000.00", "expenses": "220.50", "result": "4779.50"},
        )
        # August and September.
        self.assertEqual(
            (flow["previous_income"], flow["previous_expenses"], flow["previous_result"]),
            ("0.00", "70.00", "-70.00"),
        )

    def test_the_server_gives_the_changes_and_the_averages(self):
        self.records()
        flow = self.flow(start="2026-10", end="2026-11")
        self.assertEqual(
            (flow["income_change"], flow["expenses_change"], flow["result_change"]),
            ("5000.00", "150.50", "4849.50"),
        )
        # 150.50 more than 70.00 is 215.0%. Income had nothing before: no percentage.
        self.assertEqual(
            (flow["expenses_change_percent"], flow["income_change_percent"]), ("215.0", None)
        )
        self.assertEqual((flow["average_income"], flow["average_expenses"]), ("2500.00", "110.25"))
        food, fun = flow["categories"]
        self.assertEqual(
            (food["change"], food["share"], food["average"]), ("90.50", "72.8", "80.25")
        )
        self.assertEqual((fun["change"], fun["share"], fun["average"]), ("60.00", "27.2", "30.00"))

    def test_the_months_add_up_to_the_totals_and_agree_with_the_month_read(self):
        self.records()
        flow = self.flow(start="2026-09", end="2026-11")
        month = self.get("/api/reports/month", month="2026-11").json()["result"][0]
        self.assertEqual(
            (flow["months"][-1]["income"], flow["months"][-1]["expenses"]),
            (month["income"], month["expenses"]),
        )
        self.assertEqual(flow["expenses"], "220.50")

    def test_a_period_without_records_has_no_flow(self):
        self.assertEqual(self.analysis()["flows"], [])


class CategoryTests(AnalysisTestCase):
    def test_a_category_has_its_total_its_months_and_the_period_before(self):
        self.records()
        categories = self.flow(start="2026-10", end="2026-11")["categories"]
        self.assertEqual(
            categories,
            [
                {
                    "category_id": self.food.pk,
                    "name": "Alimentação",
                    "amount": "160.50",
                    "previous": "70.00",
                    "change": "90.50",
                    "share": "72.8",
                    "average": "80.25",
                    "months": ["40.00", "120.50"],
                },
                {
                    "category_id": self.fun.pk,
                    "name": "Lazer",
                    "amount": "60.00",
                    "previous": "0.00",
                    "change": "60.00",
                    "share": "27.2",
                    "average": "30.00",
                    "months": ["0.00", "60.00"],
                },
            ],
        )

    def test_a_category_of_the_period_before_alone_is_listed_last_with_zero(self):
        self.records()
        self.record(title="Show", amount="90.00", category_id=self.fun.pk, date="2026-07-03")
        # Period: October. Period before: September. Nothing of July counts.
        self.assertEqual(
            [row["name"] for row in self.flow(start="2026-10", end="2026-10")["categories"]],
            ["Alimentação"],
        )
        # Period: August. Period before: July.
        rows = self.flow(start="2026-08", end="2026-08")["categories"]
        self.assertEqual(
            [(row["name"], row["amount"], row["previous"]) for row in rows],
            [("Alimentação", "70.00", "0.00"), ("Lazer", "0.00", "90.00")],
        )

    def test_the_categories_add_up_to_the_expenses(self):
        self.records()
        flow = self.flow(start="2026-06", end="2026-11")
        cents = sum(round(float(row["amount"]) * 100) for row in flow["categories"])
        self.assertEqual(cents, round(float(flow["expenses"]) * 100))


class WorthTests(AnalysisTestCase):
    def test_the_net_worth_of_each_month_agrees_with_the_net_worth_read(self):
        self.records()
        self.invest()
        worth = self.analysis(start="2026-09", end="2026-11")["worth"]
        series = self.get("/api/reports/net-worth").json()["months"]
        shared = ("month", "accounts", "investments", "card_debt", "net_worth", "complete")
        self.assertEqual(
            [{name: row[name] for name in shared} for row in worth["months"]],
            [{name: row[name] for name in shared} for row in series[-3:]],
        )
        # The value at the end of the month before the period, for the change.
        self.assertEqual(worth["before"], series[-4]["net_worth"])
        self.assertEqual((worth["currency"], worth["complete"]), ("BRL", True))

    def test_the_investments_of_a_month_come_with_their_cost(self):
        self.invest()
        months = self.analysis(start="2026-08", end="2026-10")["worth"]["months"]
        self.assertEqual(
            [
                (row["investments"], row["investments_cost"], row["investments_gain"])
                for row in months
            ],
            [
                ("0.00", "0.00", "0.00"),
                ("2000.00", "2000.00", "0.00"),
                ("2000.00", "2000.00", "0.00"),
            ],
        )

    def test_the_change_of_the_period_is_against_the_month_before_it(self):
        self.invest()
        # The account has 1000.00 from the start; the position adds 2000.00 in September.
        worth = self.analysis(start="2026-09", end="2026-10")["worth"]
        self.assertEqual(
            (worth["before"], worth["change"], worth["change_percent"]),
            ("1000.00", "2000.00", "200.0"),
        )
        self.assertEqual(
            (worth["investments_before"], worth["investments_change"]), ("0.00", "2000.00")
        )

    def test_the_positions_at_the_end_of_the_period_are_listed_by_value(self):
        self.invest()
        self.invest(name="Tesouro", opening_balance="5000.00", opening_date="2026-10-20")
        positions = self.analysis(start="2026-10", end="2026-11")["positions"]
        self.assertEqual(
            [
                (row["name"], row["institution_name"], row["value"], row["share"])
                for row in positions
            ],
            [("Tesouro", "Nubank", "5000.00", "71.4"), ("Reserva", "Nubank", "2000.00", "28.6")],
        )
        # At the end of September the second position did not exist.
        positions = self.analysis(start="2026-09", end="2026-09")["positions"]
        self.assertEqual([row["name"] for row in positions], ["Reserva"])


class AccessTests(AnalysisTestCase):
    def test_the_analysis_is_the_owners_only(self):
        self.records()
        self.invest()
        self.client.force_login(self.other)
        body = self.analysis()
        self.assertEqual((body["flows"], body["positions"]), ([], []))
        self.assertEqual(body["first"], date(2026, 11, 1).isoformat())
        self.assertEqual({row["net_worth"] for row in body["worth"]["months"]}, {"0.00"})

    def test_the_analysis_needs_a_session(self):
        self.client.logout()
        self.assertEqual(self.get(URL).status_code, 401)


class MonthOriginTests(AnalysisTestCase):
    """What the figures of one month of the analysis are made of."""

    ORIGIN = "/api/reports/analysis/month"

    def origin(self, month):
        response = self.get(self.ORIGIN, month=month)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_the_entries_of_a_month_add_up_to_its_bars(self):
        self.records()
        body = self.origin("2026-11")
        self.assertEqual(body["month"], "2026-11-01")
        rows = [(row["flow"], row["title"], row["amount"]) for row in body["entries"]]
        # Income first, then expenses; each group from the largest amount.
        self.assertEqual(
            rows,
            [
                ("INCOME", "Salário", "5000.00"),
                ("EXPENSE", "Feira", "120.50"),
                ("EXPENSE", "Cinema", "60.00"),
            ],
        )
        month = self.flow(start="2026-11", end="2026-11")["months"][0]
        cents = sum(
            round(float(row["amount"]) * 100) for row in body["entries"] if row["flow"] == "EXPENSE"
        )
        self.assertEqual(cents, round(float(month["expenses"]) * 100))

    def test_an_entry_names_its_top_level_category_and_its_record(self):
        self.records()
        feira = next(row for row in self.origin("2026-11")["entries"] if row["title"] == "Feira")
        self.assertEqual(
            (feira["category_id"], feira["category_name"], feira["currency"], feira["date"]),
            (self.food.pk, "Alimentação", "BRL", "2026-11-10"),
        )
        listed = self.get("/api/ledger/transactions", month="2026-11").json()["items"]
        self.assertIn(feira["transaction_id"], [item["id"] for item in listed])

    def test_a_split_entry_has_one_row_for_each_category(self):
        entry = self.record(title="Passeio", amount="100.00")
        for category, amount in ((self.market, "70.00"), (self.fun, "30.00")):
            TransactionSplit.objects.create(
                transaction_id=entry["id"], category=category, amount=Decimal(amount)
            )
        rows = [row for row in self.origin("2026-11")["entries"] if row["title"] == "Passeio"]
        self.assertEqual(
            sorted((row["category_name"], row["amount"], row["split"]) for row in rows),
            [("Alimentação", "70.00", True), ("Lazer", "30.00", True)],
        )

    def test_an_installment_says_its_number(self):
        self.record(
            title="Notebook", amount="900.00", instrument=f"credit:{self.card.pk}", installments=3
        )
        row = self.origin("2026-11")["entries"][0]
        self.assertEqual(
            (row["title"], row["amount"], row["installment_number"], row["installment_count"]),
            ("Notebook", "300.00", 1, 3),
        )

    def test_the_net_worth_of_a_month_lists_its_accounts_positions_and_card_debt(self):
        self.record(title="Cinema", amount="60.00", instrument=f"credit:{self.manual.pk}")
        self.invest()
        worth = self.origin("2026-11")["worth"]
        self.assertEqual((worth["as_of"], worth["currency"]), ("2026-11-10", "BRL"))
        self.assertEqual(
            [(row["name"], row["bank_name"], row["amount"]) for row in worth["accounts"]],
            [("Conta", "Nubank", "1000.00")],
        )
        self.assertEqual(
            [(row["name"], row["value"]) for row in worth["positions"]], [("Reserva", "2000.00")]
        )
        self.assertEqual(
            [(row["card_name"], row["amount"]) for row in worth["cards"]], [("Black", "60.00")]
        )
        # The parts agree with the point of the chart.
        point = self.analysis(start="2026-11", end="2026-11")["worth"]["months"][0]
        self.assertEqual(
            (point["accounts"], point["investments"], point["card_debt"]),
            ("1000.00", "2000.00", "60.00"),
        )

    def test_a_past_month_is_read_at_its_last_day(self):
        self.invest()
        september = self.origin("2026-09")["worth"]
        self.assertEqual(september["as_of"], "2026-09-30")
        self.assertEqual(len(september["positions"]), 1)
        self.assertEqual(self.origin("2026-08")["worth"]["positions"], [])

    def test_the_operations_of_a_month_are_listed_with_their_kind(self):
        position = self.invest()
        response = self.post(
            f"/api/investments/positions/{position}/operations",
            {"kind": "YIELD", "date": "2026-10-31", "amount": "15.00"},
        )
        self.assertEqual(response.status_code, 200, response.content)
        october = self.origin("2026-10")["operations"]
        self.assertEqual(
            [(row["name"], row["kind"], row["date"], row["value"]) for row in october],
            [("Reserva", "YIELD", "2026-10-31", "15.00")],
        )
        self.assertEqual(self.origin("2026-11")["operations"], [])
        # The opening position of a new investment is listed in its month.
        self.assertEqual(
            [
                (row["kind"], row["date"], row["value"])
                for row in self.origin("2026-09")["operations"]
            ],
            [("OPENING", "2026-09-15", "2000.00")],
        )

    def test_a_month_after_the_current_one_is_the_current_month(self):
        self.assertEqual(self.origin("2027-05")["month"], "2026-11-01")
        self.assertEqual(self.origin("nonsense")["month"], "2026-11-01")

    def test_the_origin_is_the_owners_only_and_needs_a_session(self):
        self.records()
        self.invest()
        self.client.force_login(self.other)
        body = self.origin("2026-11")
        self.assertEqual(
            (body["entries"], body["operations"], body["worth"]["accounts"]), ([], [], [])
        )
        self.client.logout()
        self.assertEqual(self.get(self.ORIGIN).status_code, 401)
