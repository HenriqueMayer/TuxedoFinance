"""Offline safety and pagination contracts for the opt-in personal pilot."""

import io
import json
from decimal import Decimal
from unittest import TestCase
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request

from ingestion.open_finance.client import (
    MAX_RECORDS,
    MAX_REQUESTS,
    MAX_RESPONSE_BYTES,
    PilotError,
    PluggyClient,
    _HTTPTransport,
    _NoRedirect,
)


ITEM = "10000000-0000-0000-0000-000000000001"
ACCOUNT = "20000000-0000-0000-0000-000000000001"
OTHER = "20000000-0000-0000-0000-000000000002"
ROW = "30000000-0000-0000-0000-000000000001"
SECOND_ROW = "30000000-0000-0000-0000-000000000002"
SECRET = "private-client-secret"
API_KEY = "private-api-key"


def page(rows, number=1, total=None, pages=1):
    return {
        "results": rows, "page": number,
        "total": len(rows) if total is None else total, "totalPages": pages,
    }


class FakeTransport:
    def __init__(self, *responses):
        self.responses = [{"apiKey": API_KEY}, *responses]
        self.calls = []

    def request(self, method, path, *, headers, body, timeout):
        self.calls.append((method, path, headers, body, timeout))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response if isinstance(response, bytes) else json.dumps(response).encode()


class PluggyClientTests(TestCase):
    def client(self, *responses):
        transport = FakeTransport(*responses)
        return PluggyClient("local-client", SECRET, transport), transport

    def assert_code(self, expected, operation):
        with self.assertRaises(PilotError) as caught:
            operation()
        self.assertEqual(caught.exception.code, expected)
        for secret in (SECRET, API_KEY):
            self.assertNotIn(secret, str(caught.exception))
            self.assertNotIn(secret, repr(caught.exception))

    def test_auth_only_once_and_secrets_not_in_representation(self):
        client, transport = self.client({"id": ITEM}, {"id": ITEM})
        self.assertIsNone(client.authenticate())
        client.item(ITEM)
        client.item(ITEM)
        self.assertEqual([call[0] for call in transport.calls], ["POST", "GET", "GET"])
        self.assertEqual(transport.calls[0][1], "/auth")
        self.assertEqual(json.loads(transport.calls[0][3]), {
            "clientId": "local-client", "clientSecret": SECRET,
        })
        self.assertEqual(transport.calls[1][2]["X-API-KEY"], API_KEY)
        self.assertNotIn(SECRET, repr(client))
        self.assertNotIn(API_KEY, repr(client))

    def test_context_manager_clears_secrets_even_on_failure(self):
        client, _ = self.client()
        with self.assertRaises(ValueError):
            with client:
                client.authenticate()
                raise ValueError("local failure")
        self.assertIsNone(client._api_key)
        self.assertIsNone(client._client_secret)
        self.assertIsNone(client._client_id)
        self.assert_code("closed", lambda: client.item(ITEM))

    def test_identifiers_and_dates_are_validated_before_authentication(self):
        client, transport = self.client()
        for invalid in ("../payments", ACCOUNT + "?secret=1", "not-a-uuid", None):
            self.assert_code("identifier", lambda: client.item(invalid))
        for start, end in (("2026-02-30", "2026-03-01"), ("2026-10-02", "2026-10-01"),
                           ("20261001", "2026-10-01")):
            self.assert_code("date_range", lambda: client.transactions(ACCOUNT, start, end))
        self.assertEqual(transport.calls, [])

    def test_accounts_are_card_only_and_paginated(self):
        card = {"id": ACCOUNT, "itemId": ITEM, "type": "CREDIT", "subtype": "CREDIT_CARD"}
        loan = {"id": OTHER, "itemId": ITEM, "type": "CREDIT", "subtype": "LOAN"}
        client, transport = self.client(page([card], total=2, pages=2),
                                        page([loan], number=2, total=2, pages=2))
        self.assertEqual(client.accounts(ITEM), [card])
        query = parse_qs(urlsplit(transport.calls[2][1]).query)
        self.assertEqual(query, {"itemId": [ITEM], "type": ["CREDIT"],
                                 "page": ["2"], "pageSize": ["200"]})

    def test_foreign_item_and_account_rows_are_rejected(self):
        for response, operation in (
            ({"id": OTHER}, lambda c: c.item(ITEM)),
            (page([{"id": ACCOUNT, "itemId": OTHER, "type": "CREDIT"}]),
             lambda c: c.accounts(ITEM)),
            (page([{"id": ROW, "accountId": OTHER}]), lambda c: c.bills(ACCOUNT)),
            ({"results": [{"id": ROW, "accountId": OTHER}], "next": None},
             lambda c: c.transactions(ACCOUNT, "2026-10-01", "2026-10-31")),
        ):
            with self.subTest(response=response):
                client, _ = self.client(response)
                self.assert_code("foreign_record", lambda: operation(client))

    def test_bill_decimal_amount_and_nullable_closing_date_are_preserved(self):
        raw = ('{"page":1,"total":1,"totalPages":1,"results":['
               '{"id":"' + ROW + '","totalAmount":19.99,"billClosingDate":null}]}').encode()
        client, _ = self.client(raw)
        result = client.bills(ACCOUNT)
        self.assertEqual(result[0]["totalAmount"], Decimal("19.99"))
        self.assertIsNone(result[0]["billClosingDate"])

    def test_page_metadata_mismatch_repetition_changes_and_truncation_fail(self):
        cases = [
            ("response_schema", [page([], number=2)]),
            ("pagination_repeated", [page([{"id": ROW}], total=2, pages=2),
                                     page([{"id": ROW}], number=2, total=2, pages=2)]),
            ("pagination_changed", [page([{"id": ROW}], total=2, pages=2),
                                    page([{"id": SECOND_ROW}], number=2, total=3, pages=2)]),
            ("pagination_incomplete", [page([{"id": ROW}], total=2)]),
            ("page_limit", [page([], total=11, pages=11)]),
            ("record_limit", [page([], total=MAX_RECORDS + 1)]),
            ("response_schema", [page([], total=1, pages=2)]),
        ]
        for code, responses in cases:
            with self.subTest(code=code):
                client, _ = self.client(*responses)
                self.assert_code(code, lambda: client.bills(ACCOUNT))

    def test_cursor_uses_fixed_endpoint_and_preserves_omitted_date_bounds(self):
        first = {"id": ROW, "accountId": ACCOUNT}
        second = {"id": SECOND_ROW, "accountId": ACCOUNT}
        client, transport = self.client(
            {"results": [first], "next": "?" + urlencode({"accountId": ACCOUNT, "after": "abc+/="})},
            {"results": [second], "next": None},
        )
        self.assertEqual(client.transactions(ACCOUNT, "2026-10-01", "2026-10-31"), [first, second])
        path = transport.calls[-1][1]
        self.assertTrue(path.startswith("/v2/transactions?"))
        self.assertEqual(parse_qs(urlsplit(path).query), {
            "accountId": [ACCOUNT], "dateFrom": ["2026-10-01"],
            "dateTo": ["2026-10-31"], "after": ["abc+/="],
        })

    def test_cursor_cannot_escape_scope_or_change_filters(self):
        cursor = "?" + urlencode({"accountId": ACCOUNT, "after": "a"})
        invalid = [
            "https://attacker.invalid/steal", "//attacker.invalid/steal", cursor + "#fragment",
            cursor + "&unknown=1", cursor + "&accountId=" + ACCOUNT,
            cursor + "&dateFrom=2020-01-01", cursor + "&dateTo=2030-01-01",
            "?accountId=" + ACCOUNT, cursor + "\n", "?accountId=" + ACCOUNT + "&after=%0D%0A",
        ]
        for next_query in invalid:
            with self.subTest(cursor=next_query):
                client, transport = self.client({"results": [], "next": next_query})
                self.assert_code("pagination_cursor", lambda: client.transactions(
                    ACCOUNT, "2026-10-01", "2026-10-31"))
                self.assertEqual(len(transport.calls), 2)
        client, _ = self.client({"results": [], "next": "?" + urlencode({
            "accountId": OTHER, "after": "a",
        })})
        self.assert_code("foreign_record", lambda: client.transactions(
            ACCOUNT, "2026-10-01", "2026-10-31"))

    def test_repeated_cursors_and_duplicate_transaction_ids_fail(self):
        next_query = "?" + urlencode({"accountId": ACCOUNT, "after": "a"})
        client, _ = self.client({"results": [], "next": next_query},
                                {"results": [], "next": next_query})
        self.assert_code("pagination_repeated", lambda: client.transactions(
            ACCOUNT, "2026-10-01", "2026-10-31"))
        row = {"id": ROW, "accountId": ACCOUNT}
        client, _ = self.client({"results": [row], "next": next_query},
                                {"results": [row], "next": None})
        self.assert_code("pagination_repeated", lambda: client.transactions(
            ACCOUNT, "2026-10-01", "2026-10-31"))

    def test_cursor_pages_and_global_record_budget_are_bounded(self):
        responses = [{"results": [], "next": "?" + urlencode({
            "accountId": ACCOUNT, "after": str(index),
        })} for index in range(10)]
        client, transport = self.client(*responses)
        self.assert_code("page_limit", lambda: client.transactions(
            ACCOUNT, "2026-10-01", "2026-10-31"))
        self.assertEqual(len(transport.calls), 11)
        client, _ = self.client(page([{"id": ROW}]))
        client._records = MAX_RECORDS
        self.assert_code("record_limit", lambda: client.bills(ACCOUNT))

    def test_schema_and_json_failures_do_not_expose_raw_payloads(self):
        for payload in (
            b"<html>" + SECRET.encode(), b"[]", b'{"results":NaN}',
            b'{"apiKey":"first","apiKey":"second"}',
            b'{"page":true,"total":0,"totalPages":1,"results":[]}',
            b'{"page":1,"total":1,"totalPages":1,"results":[null]}',
        ):
            with self.subTest(payload=payload):
                client, _ = self.client(payload)
                self.assert_code("response_schema", lambda: client.bills(ACCOUNT))

    def test_response_size_request_and_elapsed_budgets(self):
        client, _ = self.client(b" " * (MAX_RESPONSE_BYTES + 1))
        self.assert_code("response_limit", lambda: client.item(ITEM))
        client, transport = self.client()
        client._requests = MAX_REQUESTS
        self.assert_code("request_limit", client.authenticate)
        self.assertEqual(transport.calls, [])
        client, transport = self.client()
        with patch("ingestion.open_finance.client.time.monotonic", return_value=client._started + 61):
            self.assert_code("time_limit", client.authenticate)
        self.assertEqual(transport.calls, [])

    def test_transport_exception_is_redacted(self):
        client, _ = self.client(ValueError(SECRET + API_KEY))
        self.assert_code("response_schema", lambda: client.item(ITEM))
        client, _ = self.client(RuntimeError(SECRET + API_KEY))
        self.assert_code("connection", lambda: client.item(ITEM))

    def test_private_request_and_transport_allow_only_pilot_endpoints(self):
        client, transport = self.client()
        for method, path in (("GET", "/payments/customers"), ("PATCH", "/items/" + ITEM),
                             ("GET", "https://attacker.invalid"), ("GET", "//attacker.invalid"),
                             ("POST", "/connect_token"), ("GET", "/v2/items"),
                             ("GET", "/accounts?itemId=" + ITEM + "&type=BANK&page=1&pageSize=200")):
            with self.subTest(method=method, path=path):
                self.assert_code("endpoint", lambda: client._request(method, path))
        self.assertEqual(transport.calls, [])

    def test_authentication_rejects_missing_and_header_injection_keys(self):
        for response in ({}, {"apiKey": "key\r\nHeader: value"}, {"apiKey": None}):
            transport = FakeTransport()
            transport.responses = [response]
            client = PluggyClient("local-client", SECRET, transport)
            self.assert_code("response_schema", client.authenticate)


class PluggyHTTPTransportTests(TestCase):
    def test_redirect_handler_does_not_create_second_request(self):
        handler = _NoRedirect()
        with self.assertRaises(PilotError) as caught:
            handler.redirect_request(Request("https://api.pluggy.ai/auth"), None, 302,
                                     "Found", {}, "https://attacker.invalid")
        self.assertEqual(caught.exception.code, "redirect")

    def test_fixed_origin_and_response_size_limit(self):
        transport = _HTTPTransport()
        response = MagicMock()
        response.status = 200
        response.read1.side_effect = [b"{}", b""]
        transport.opener.open = MagicMock()
        transport.opener.open.return_value.__enter__.return_value = response
        self.assertEqual(transport.request("POST", "/auth", headers={}, body=b"{}", timeout=10), b"{}")
        request = transport.opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.pluggy.ai/auth")
        response.read1.side_effect = [b"x" * (MAX_RESPONSE_BYTES + 1)]
        with self.assertRaises(PilotError) as caught:
            transport.request("POST", "/auth", headers={}, body=b"{}", timeout=10)
        self.assertEqual(caught.exception.code, "response_limit")

    def test_http_statuses_are_safe_and_have_distinct_diagnostics(self):
        transport = _HTTPTransport()
        for status, code in ((401, "unauthorized"), (403, "forbidden"),
                             (404, "not_found"), (429, "rate_limited"),
                             (503, "provider_unavailable"), (302, "redirect")):
            with self.subTest(status=status):
                transport.opener.open = MagicMock(side_effect=HTTPError(
                    "https://api.pluggy.ai/" + SECRET, status, SECRET,
                    {}, io.BytesIO(SECRET.encode()),
                ))
                with self.assertRaises(PilotError) as caught:
                    transport.request("POST", "/auth", headers={}, body=b"{}", timeout=10)
                self.assertEqual(caught.exception.code, code)
                self.assertNotIn(SECRET, str(caught.exception))
