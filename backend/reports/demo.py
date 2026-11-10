"""The data of the public demonstration.

``export(language)`` creates one fictional owner, records about four months
of ordinary financial life through the API, and then reads every screen of
the client through the API. The result is the set of answers that the public
site serves from static files, so the demonstration shows what the real
operations calculate and no rule is written twice.

The dates are relative to the *demonstration day*: the latest 18th on or
before the day of the export. A month that is two thirds over shows every
screen with data, whatever the day of the build. During the export that day
is today for every rule, and the client shows it as today.

``export`` writes to the configured database and refuses to run when it
already has a user. Run it with a temporary data directory
(``site/scripts/build.sh``).
"""

import calendar
import json
from datetime import date
from decimal import Decimal
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client

from config import clock
from ledger import schedule
from ledger.categories import Category

USERNAME = "demo"
MONTHS_BACK = 4
MONTHS_READ_BACK = 12
MONTHS_READ_AHEAD = 2
DEMONSTRATION_DAY = 18

TEXTS = {
    "en": {
        "checking": "Checking",
        "savings": "Savings",
        "dollars": "Dollars",
        "housing": "Housing",
        "rent": "Rent",
        "utilities": "Building fee",
        "internet": "Internet",
        "groceries": "Groceries",
        "eating_out": "Eating out",
        "transport": "Transport",
        "leisure": "Leisure",
        "streaming": "Streaming",
        "health": "Health",
        "education": "Education",
        "salary": "Salary",
        "freelance": "Freelance",
        "market": ("Corner market", "Farmers market", "Supermarket", "Bakery"),
        "restaurant": ("Pizza night", "Lunch downtown", "Sushi", "Coffee and cake"),
        "ride": ("Ride home", "Subway card", "Fuel", "Parking"),
        "cinema": "Cinema",
        "pharmacy": "Pharmacy",
        "gym": "Gym",
        "course": "Design course",
        "notebook": "Notebook",
        "freelance_job": "Website for a client",
        "emergency": "Emergency fund",
        "shares": "Global ETF",
        "trip": "Trip to Japan",
        "points": "points",
        "ticket": "Flight to Recife",
        "sheet": "Moving to a new flat",
        "moving": "Movers and deposit",
    },
    "pt-BR": {
        "checking": "Conta",
        "savings": "Reserva",
        "dollars": "Dólares",
        "housing": "Moradia",
        "rent": "Aluguel",
        "utilities": "Condomínio",
        "internet": "Internet",
        "groceries": "Mercado",
        "eating_out": "Restaurantes",
        "transport": "Transporte",
        "leisure": "Lazer",
        "streaming": "Streaming",
        "health": "Saúde",
        "education": "Educação",
        "salary": "Salário",
        "freelance": "Freela",
        "market": ("Mercado da esquina", "Feira", "Supermercado", "Padaria"),
        "restaurant": ("Pizza", "Almoço no centro", "Sushi", "Café e bolo"),
        "ride": ("Corrida para casa", "Bilhete do metrô", "Gasolina", "Estacionamento"),
        "cinema": "Cinema",
        "pharmacy": "Farmácia",
        "gym": "Academia",
        "course": "Curso de design",
        "notebook": "Notebook",
        "freelance_job": "Site para cliente",
        "emergency": "Reserva de emergência",
        "shares": "ETF global",
        "trip": "Viagem ao Japão",
        "points": "pontos",
        "ticket": "Passagem para Recife",
        "sheet": "Mudança de apartamento",
        "moving": "Mudança e caução",
    },
}


class _Api:
    """The API as the signed-in demonstration owner. A refused call stops the export."""

    def __init__(self, user, language):
        # The test client names a host that only the test runner allows.
        host = next((name for name in settings.ALLOWED_HOSTS if name[:1] not in "*."), "localhost")
        self.client = Client(headers={"accept-language": language}, SERVER_NAME=host)
        self.client.force_login(user)

    def send(self, method, path, payload=None):
        response = getattr(self.client, method)(
            path, data=json.dumps(payload or {}), content_type="application/json"
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"{method.upper()} {path} {response.status_code}: {response.content!r}"
            )
        return response.json() if response.content else None

    def post(self, path, payload=None):
        return self.send("post", path, payload)

    def put(self, path, payload=None):
        return self.send("put", path, payload)

    def get(self, path, query=None):
        response = self.client.get(path, query or {})
        if response.status_code >= 400:
            raise RuntimeError(f"GET {path} {query} {response.status_code}: {response.content!r}")
        return response.json()


def _on(today, months_back, day):
    """Return the day ``day`` of the month ``months_back`` months ago, inside that month."""
    month = schedule.offset_month(today, -months_back)
    return month.replace(day=min(day, calendar.monthrange(month.year, month.month)[1]))


def _vary(base, months_back, day):
    """Return an amount near ``base`` that differs by month and day, the same on every run."""
    cents = (months_back * 731 + day * 197) % 1900
    return f"{Decimal(base) + Decimal(cents) / 100:.2f}"


def seed(user, language):
    """Record the financial life of the demonstration owner through the API."""
    text = TEXTS[language]
    api = _Api(user, language)
    today = clock.today()
    start = _on(today, MONTHS_BACK, 1)

    # The categories of a new owner come in the language of the creation; these replace them.
    Category.objects.filter(user=user).delete()

    def category(name, kind="EXPENSE", parent=None):
        payload = {"name": text[name], "transaction_type": kind, "parent_id": parent}
        return api.post("/api/ledger/categories", payload)["id"]

    housing = category("housing")
    rent, internet = category("rent", parent=housing), category("internet", parent=housing)
    groceries, eating_out = category("groceries"), category("eating_out")
    transport, leisure = category("transport"), category("leisure")
    streaming = category("streaming", parent=leisure)
    health, education = category("health"), category("education")
    salary, freelance = category("salary", "INCOME"), category("freelance", "INCOME")

    def account(bank, name, balance, currency="BRL"):
        return api.post(
            "/api/banking/accounts",
            {
                "bank_name": bank,
                "name": text[name],
                "currency": currency,
                "opening_balance": balance,
                "opening_date": start.isoformat(),
            },
        )["id"]

    checking = account("Nubank", "checking", "2640.00")
    savings = account("Nubank", "savings", "0")
    account("Wise", "dollars", "350.00", "USD")
    platinum = api.post(
        "/api/banking/credit-cards",
        {"account": checking, "name": "Platinum", "closing_day": 24, "due_day": 1},
    )["id"]
    black = api.post(
        "/api/banking/credit-cards",
        {
            "account": checking,
            "name": "Black",
            "closing_day": 20,
            "due_day": 28,
            "confirm_payments": True,
        },
    )["id"]
    # A rate from the first month on, so that every month end has its net worth.
    for months_back, rate in ((MONTHS_BACK, "5.18"), (2, "5.31"), (0, "5.42")):
        api.post(
            "/api/banking/exchange-rates",
            {
                "from_currency": "USD",
                "rate": rate,
                "effective_date": _on(today, months_back, 1).isoformat(),
            },
        )

    def entry(title, amount, category_id, instrument, when, **more):
        if when > today and not more.get("is_fixed"):
            return None
        return api.post(
            "/api/ledger/transactions",
            {
                "title": title,
                "amount": amount,
                "category_id": category_id,
                "instrument": instrument,
                "date": when.isoformat(),
                **more,
            },
        )

    # What repeats every month.
    entry(
        text["salary"],
        "7400.00",
        salary,
        checking,
        _on(today, MONTHS_BACK, 5),
        transaction_type="INCOME",
        is_fixed=True,
    )
    entry(text["rent"], "2600.00", rent, checking, _on(today, MONTHS_BACK, 10), is_fixed=True)
    entry(
        text["utilities"], "418.70", housing, checking, _on(today, MONTHS_BACK, 12), is_fixed=True
    )
    entry(
        text["internet"],
        "119.90",
        internet,
        checking,
        _on(today, 1, 15),
        is_fixed=True,
        requires_confirmation=True,
    )
    entry(text["streaming"], "55.90", streaming, platinum, _on(today, 3, 8), is_fixed=True)
    entry(text["gym"], "129.90", health, black, _on(today, 3, 12), is_fixed=True)

    # Purchases of each month.
    for months_back in range(MONTHS_BACK, -1, -1):
        for index, day in enumerate((3, 9, 17, 24)):
            entry(
                text["market"][index],
                _vary("172.00", months_back, day),
                groceries,
                platinum if index % 2 else checking,
                _on(today, months_back, day),
            )
        for index, day in enumerate((6, 13, 21, 27)):
            entry(
                text["restaurant"][index],
                _vary("74.00", months_back, day),
                eating_out,
                black if index % 2 else platinum,
                _on(today, months_back, day),
            )
        for index, day in enumerate((2, 11, 19, 26)):
            entry(
                text["ride"][index],
                _vary("31.00", months_back, day),
                transport,
                checking,
                _on(today, months_back, day),
            )
        entry(
            text["cinema"],
            _vary("58.00", months_back, 14),
            leisure,
            black,
            _on(today, months_back, 14),
        )
        entry(
            text["pharmacy"],
            _vary("41.00", months_back, 18),
            health,
            checking,
            _on(today, months_back, 18),
        )
    entry(text["notebook"], "4800.00", education, platinum, _on(today, 2, 12), installments=8)
    entry(text["course"], "390.00", education, platinum, _on(today, 1, 16))
    for months_back in (3, 1):
        entry(
            text["freelance_job"],
            "1500.00",
            freelance,
            checking,
            _on(today, months_back, 22),
            transaction_type="INCOME",
        )

    # Money that the owner keeps aside.
    number = lambda instrument: int(instrument.split(":")[1])  # noqa: E731
    for months_back in range(MONTHS_BACK - 1, -1, -1):
        when = _on(today, months_back, 6)
        if when <= today:
            api.post(
                "/api/banking/transfers",
                {
                    "source_account_id": number(checking),
                    "destination_account_id": number(savings),
                    "amount": "800.00",
                    "date": when.isoformat(),
                },
            )
    emergency = api.post(
        "/api/investments/positions",
        {
            "name": text["emergency"],
            "institution_name": "Nubank",
            "opening_balance": "9000.00",
            "opening_date": start.isoformat(),
        },
    )["id"]
    for months_back in (3, 2, 1):
        api.post(
            f"/api/investments/positions/{emergency}/operations",
            {
                "kind": "DEPOSIT",
                "amount": "600.00",
                "account_id": number(checking),
                "date": _on(today, months_back, 7).isoformat(),
            },
        )
    api.post(f"/api/investments/positions/{emergency}/value", {"value": "11014.37"})
    shares = api.post(
        "/api/investments/positions",
        {
            "name": text["shares"],
            "institution_name": "XP",
            "valuation_mode": "UNITS",
            "opening_quantity": "30",
            "opening_unit_price": "38.50",
            "opening_date": _on(today, 3, 1).isoformat(),
        },
    )["id"]
    api.post(f"/api/investments/positions/{shares}/value", {"value": "41.20"})

    # What the owner intends.
    limit_from = _on(today, 2, 1).isoformat()
    api.put("/api/plan/limit", {"month": limit_from, "amount": "6000.00"})
    for category_id, amount in (
        (groceries, "900.00"),
        (eating_out, "300.00"),
        (leisure, "350.00"),
    ):
        api.put(
            "/api/plan/limit", {"month": limit_from, "amount": amount, "category_id": category_id}
        )
    fund = api.post("/api/plan/goals", {"name": text["emergency"], "target_amount": "30000.00"})[
        "id"
    ]
    api.put(
        f"/api/plan/goals/{fund}/reservations",
        {"source": f"investment:{emergency}", "amount": "10800.00"},
    )
    trip = api.post(
        "/api/plan/goals",
        {
            "name": text["trip"],
            "target_amount": "15000.00",
            "target_date": schedule.offset_month(today, 10).isoformat(),
        },
    )["id"]
    api.put(f"/api/plan/goals/{trip}/reservations", {"source": savings, "amount": "2400.00"})
    api.post(
        "/api/plan/sheets",
        {
            "name": text["sheet"],
            "months": 6,
            "changes": {
                "manual": [
                    {"id": "moving", "label": text["moving"], "section": "expense", "amount": None}
                ],
                "cells": {
                    "manual:moving": {schedule.offset_month(today, 2).strftime("%Y-%m"): "3200.00"}
                },
            },
        },
    )
    api.post("/api/plan/closing", {"month": _on(today, 2, 1).isoformat()})

    # Points.
    program = api.post("/api/loyalty/programs", {"name": "Livelo", "unit_name": text["points"]})[
        "id"
    ]
    api.post(f"/api/loyalty/programs/{program}/entries", {"kind": "EARNED", "amount": "24500"})
    api.post(
        f"/api/loyalty/programs/{program}/entries",
        {"kind": "USED", "amount": "6000", "notes": text["ticket"]},
    )


def _key(method, path, query=None):
    """Return the name of a recorded answer: the method, the path and the sorted query."""
    pairs = sorted((name, str(value)) for name, value in (query or {}).items())
    text = "&".join(f"{name}={value}" for name, value in pairs)
    return f"{method} {path}?{text}" if text else f"{method} {path}"


def record(user, language):
    """Read every screen of the client as ``user``.

    Return ``{key: answer}`` for the reads, and the calculated sheets as a
    list of ``{"months", "changes", "answer"}``.
    """
    api = _Api(user, language)
    today = clock.today()
    answers = {}

    def get(path, **query):
        answers[_key("GET", path, query)] = body = api.get(path, query)
        return body

    for path in (
        "/api/session",
        "/api/reports/home",
        "/api/reports/net-worth",
        "/api/reports/month",
        "/api/ledger/categories",
        "/api/banking/instruments",
        "/api/banking/exchange-rates",
        "/api/plan/month",
        "/api/plan/forecast",
        "/api/plan/closing",
        "/api/imports",
        "/api/ledger/transactions/suggestion",
    ):
        get(path)

    # The lists that a month selects, with every page of each.
    def transactions(**query):
        page = get("/api/ledger/transactions", **query)
        for number in range(2, page["pages"] + 1):
            get("/api/ledger/transactions", **query, page=number)
        return page

    titles = set()
    identifiers = set()
    for offset in range(-MONTHS_READ_BACK, MONTHS_READ_AHEAD + 1):
        month = schedule.offset_month(today, offset).strftime("%Y-%m")
        get("/api/reports/month", month=month)
        if offset <= 0:
            get("/api/plan/closing", month=month)
        key = _key("GET", "/api/ledger/transactions", {"month": month})
        transactions(month=month)
        for name, body in answers.items():
            if name.startswith(key):
                titles.update(item["title"] for item in body["items"])
                identifiers.update(item["id"] for item in body["items"])
    transactions()

    # The analysis: every period that the presets and the slider can reach.
    # The oldest start is the oldest record, the twelve-month preset or the
    # first month of the year, whichever comes first.
    current = today.replace(day=1)
    oldest = min(
        date.fromisoformat(get("/api/reports/analysis")["first"]),
        schedule.offset_month(current, -11),
        current.replace(month=1),
    )
    span = schedule.months_between(oldest, current.year, current.month) + 1
    reachable = [schedule.offset_month(oldest, offset).strftime("%Y-%m") for offset in range(span)]
    for index, start in enumerate(reachable):
        # What each month is made of, for a click on a chart.
        get("/api/reports/analysis/month", month=start)
        for end in reachable[index:]:
            get("/api/reports/analysis", start=start, end=end)

    for title in sorted(titles):
        get("/api/ledger/transactions/suggestion", title=title)

    # Each record that a window opens.
    for identifier in sorted(identifiers):
        item = get(f"/api/ledger/transactions/{identifier}")
        if item["is_fixed"]:
            get(f"/api/ledger/transactions/{identifier}/schedule")
    wallet = get("/api/banking/wallet")
    invoices = set()
    for bank in wallet["banks"]:
        for account in bank["accounts"]:
            get(f"/api/banking/accounts/{account['id']}")
            for card in account["credit_cards"]:
                detail = get(f"/api/banking/credit-cards/{card['id']}")
                invoices.update(invoice["id"] for invoice in detail["invoices"])
    invoices.update(
        row["invoice_id"] for row in answers["GET /api/reports/home"]["due"] if row["invoice_id"]
    )
    for identifier in sorted(invoices):
        get(f"/api/banking/invoices/{identifier}")
    for position in get("/api/investments/positions")["positions"]:
        get(f"/api/investments/positions/{position['id']}")
    for program in get("/api/loyalty/programs"):
        get(f"/api/loyalty/programs/{program['id']}")
    get("/api/plan/goals")
    # The sheet is calculated by a POST. It is recorded for the two periods
    # without changes and for the changes of each saved sheet.
    empty = {"cells": {}, "manual": []}
    wanted = [(6, empty), (12, empty)]
    for sheet in get("/api/plan/sheets"):
        saved = get(f"/api/plan/sheets/{sheet['id']}")
        wanted.append((saved["months"], saved["changes"]))
    sheets = [
        {
            "months": months,
            "changes": changes,
            "answer": api.post("/api/plan/sheet", {"months": months, "changes": changes}),
        }
        for months, changes in wanted
    ]
    return answers, sheets


def demonstration_day(today):
    """Return the latest 18th on or before ``today``."""
    if today.day >= DEMONSTRATION_DAY:
        return today.replace(day=DEMONSTRATION_DAY)
    return schedule.offset_month(today, -1).replace(day=DEMONSTRATION_DAY)


def export(language):
    """Create the demonstration owner and return the data file of ``language``."""
    users = get_user_model().objects
    if users.exists():
        raise RuntimeError(
            "The database already has a user. The demonstration is exported from an empty, "
            "temporary database only."
        )
    day = demonstration_day(clock.today())
    # ``config.clock`` reads this function at each call, so every rule sees the day.
    with mock.patch("django.utils.timezone.localdate", return_value=day):
        user = users.create_user(USERNAME, "demo@example.test")
        seed(user, language)
        answers, sheets = record(user, language)
    return {
        "language": language,
        "today": day.isoformat(),
        "answers": answers,
        "sheets": sheets,
    }


def write(language, path):
    """Export the demonstration of ``language`` to the JSON file ``path``."""
    data = export(language)
    with open(path, "w", encoding="utf-8") as output:
        json.dump(data, output, ensure_ascii=False, separators=(",", ":"))
    return len(data["answers"])
