# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Bounded Meu Pluggy reads; this adapter never writes financial records."""

import json
import math
import socket
import time
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    ProxyHandler,
    Request,
    build_opener,
)
from uuid import UUID


MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_REQUESTS = 20
MAX_PAGES = 10
MAX_RECORDS = 2000
REQUEST_TIMEOUT = 10
TOTAL_TIMEOUT = 60
PAGE_SIZE = 200
API_ORIGIN = "https://api.pluggy.ai"


class PilotError(Exception):
    """A safe diagnostic code, without provider payloads or credential values."""

    def __init__(self, code):
        self.code = code
        super().__init__(f"Pluggy pilot could not continue ({code}).")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise PilotError("redirect")


class _HTTPTransport:
    """Fixed-origin transport with no redirects or environment proxy settings."""

    def __init__(self):
        self.opener = build_opener(ProxyHandler({}), HTTPSHandler(), _NoRedirect())

    def request(self, method, path, *, headers, body, timeout):
        _endpoint(method, path)
        request = Request(API_ORIGIN + path, data=body, headers=headers, method=method)
        started = time.monotonic()
        try:
            with self.opener.open(request, timeout=timeout) as response:
                if response.status != 200:
                    raise PilotError("http_error")
                chunks = []
                size = 0
                # read1 returns after one underlying read, allowing an elapsed
                # budget check even when a server slowly streams a JSON body.
                read = getattr(response, "read1", response.read)
                while True:
                    if time.monotonic() - started >= timeout:
                        raise PilotError("timeout")
                    chunk = read(min(64 * 1024, MAX_RESPONSE_BYTES + 1 - size))
                    if not chunk:
                        return b"".join(chunks)
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        raise PilotError("response_limit")
                    chunks.append(chunk)
        except HTTPError as exc:
            code = {
                401: "unauthorized", 403: "forbidden", 404: "not_found",
                429: "rate_limited", 500: "provider_unavailable",
                502: "provider_unavailable", 503: "provider_unavailable",
                504: "provider_unavailable",
            }.get(exc.code, "redirect" if 300 <= exc.code < 400 else "http_error")
            exc.close()
            raise PilotError(code) from None
        except (TimeoutError, socket.timeout):
            raise PilotError("timeout") from None
        except (URLError, OSError, ValueError):
            raise PilotError("connection") from None


def _uuid(value):
    if not isinstance(value, str) or len(value) != 36:
        raise PilotError("identifier")
    try:
        return str(UUID(value))
    except ValueError:
        raise PilotError("identifier") from None


def _day(value):
    if not isinstance(value, str):
        raise PilotError("date_range")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise PilotError("date_range") from None
    if parsed.isoformat() != value:
        raise PilotError("date_range")
    return value


def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _endpoint(method, path):
    """Keep even internal/injected transport calls inside the read allowlist."""
    if (not isinstance(path, str) or not path.startswith("/")
            or path.startswith("//") or "#" in path
            or any(ord(char) < 33 or ord(char) > 126 for char in path)):
        raise PilotError("endpoint")
    parsed = urlsplit(path)
    if parsed.scheme or parsed.netloc:
        raise PilotError("endpoint")
    if method == "POST" and path == "/auth":
        return
    if method != "GET":
        raise PilotError("endpoint")
    if parsed.path.startswith("/items/") and not parsed.query:
        _uuid(parsed.path.removeprefix("/items/"))
        return
    expected = {
        "/accounts": {"itemId", "type", "page", "pageSize"},
        "/bills": {"accountId", "page", "pageSize"},
        "/v2/transactions": {"accountId", "dateFrom", "dateTo", "after"},
    }.get(parsed.path)
    if expected is None:
        raise PilotError("endpoint")
    try:
        pairs = parse_qsl(parsed.query, strict_parsing=True, max_num_fields=5)
    except ValueError:
        raise PilotError("endpoint") from None
    fields = dict(pairs)
    if len(fields) != len(pairs) or not set(fields) <= expected:
        raise PilotError("endpoint")
    if parsed.path == "/accounts":
        _uuid(fields.get("itemId"))
        if fields.get("type") != "CREDIT":
            raise PilotError("endpoint")
    else:
        _uuid(fields.get("accountId"))
    if parsed.path == "/v2/transactions":
        if _day(fields.get("dateFrom")) > _day(fields.get("dateTo")):
            raise PilotError("date_range")
    else:
        for key, maximum in (("page", MAX_PAGES), ("pageSize", PAGE_SIZE)):
            value = fields.get(key, "")
            if not value.isascii() or not value.isdecimal() or not 1 <= int(value) <= maximum:
                raise PilotError("endpoint")


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PilotError("response_schema")
        result[key] = value
    return result


def _invalid_number(value):
    raise PilotError("response_schema")


class PluggyClient:
    """Short-lived client; only auth and the pilot's four read paths exist.

    A test transport implements request(method, path, *, headers, body, timeout)
    and returns JSON bytes. Credentials and API keys are kept in memory only.
    """

    def __init__(self, client_id, client_secret, transport=None):
        if any(not isinstance(value, str) or not value or len(value) > 4096
               for value in (client_id, client_secret)):
            raise PilotError("configuration")
        self._client_id = client_id
        self._client_secret = client_secret
        self._api_key = None
        self._transport = transport if transport is not None else _HTTPTransport()
        self._closed = False
        self._requests = 0
        self._records = 0
        self._started = time.monotonic()

    def __enter__(self):
        self._check_open()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        self._api_key = None
        self._client_id = None
        self._client_secret = None
        self._closed = True

    def _check_open(self):
        if self._closed:
            raise PilotError("closed")

    def _remaining(self):
        remaining = TOTAL_TIMEOUT - (time.monotonic() - self._started)
        if not math.isfinite(remaining) or remaining <= 0:
            raise PilotError("time_limit")
        return min(REQUEST_TIMEOUT, remaining)

    def _request(self, method, path, body=None):
        self._check_open()
        _endpoint(method, path)
        timeout = self._remaining()
        if self._requests >= MAX_REQUESTS:
            raise PilotError("request_limit")
        self._requests += 1
        headers = {"Accept": "application/json"}
        if method == "POST":
            if path != "/auth":
                raise PilotError("endpoint")
            headers["Content-Type"] = "application/json"
        elif method == "GET":
            if not self._api_key:
                raise PilotError("unauthorized")
            headers["X-API-KEY"] = self._api_key
        else:
            raise PilotError("endpoint")
        try:
            raw = self._transport.request(
                method, path, headers=headers, body=body, timeout=timeout,
            )
            self._remaining()
            if not isinstance(raw, bytes):
                raise PilotError("response_schema")
            if len(raw) > MAX_RESPONSE_BYTES:
                raise PilotError("response_limit")
            response = json.loads(
                raw, parse_float=Decimal, parse_constant=_invalid_number,
                object_pairs_hook=_json_object,
            )
        except PilotError:
            raise
        except (TimeoutError, socket.timeout):
            raise PilotError("timeout") from None
        except (UnicodeError, ValueError, InvalidOperation, RecursionError):
            raise PilotError("response_schema") from None
        except Exception:
            # A transport exception can contain its URL, body or authorization
            # headers. It must not escape through the CLI's error reporting.
            raise PilotError("connection") from None
        if not isinstance(response, dict):
            raise PilotError("response_schema")
        return response

    def authenticate(self):
        self._check_open()
        if self._api_key is not None:
            return None
        payload = json.dumps({
            "clientId": self._client_id, "clientSecret": self._client_secret,
        }).encode("utf-8")
        response = self._request("POST", "/auth", payload)
        key = response.get("apiKey")
        if (not isinstance(key, str) or not key or len(key) > 16384
                or any(ord(char) < 33 or ord(char) > 126 for char in key)):
            raise PilotError("response_schema")
        self._api_key = key
        return None

    def item(self, item_id):
        item_id = _uuid(item_id)
        self.authenticate()
        result = self._request("GET", f"/items/{item_id}")
        if _uuid(result.get("id")) != item_id:
            raise PilotError("foreign_record")
        return result

    def _rows(self, response, seen):
        rows = response.get("results")
        if not isinstance(rows, list):
            raise PilotError("response_schema")
        self._records += len(rows)
        if self._records > MAX_RECORDS:
            raise PilotError("record_limit")
        for row in rows:
            if not isinstance(row, dict):
                raise PilotError("response_schema")
            identifier = _uuid(row.get("id"))
            if identifier in seen:
                raise PilotError("pagination_repeated")
            seen.add(identifier)
        return rows

    def _pages(self, endpoint, query):
        self.authenticate()
        result = []
        seen = set()
        expected_total = expected_pages = None
        for page in range(1, MAX_PAGES + 1):
            response = self._request("GET", endpoint + "?" + urlencode({
                **query, "page": page, "pageSize": PAGE_SIZE,
            }))
            current_page = response.get("page")
            total_pages = response.get("totalPages")
            total = response.get("total")
            if (not all(_integer(value) for value in (current_page, total_pages, total))
                    or current_page != page or (total and not total_pages)):
                raise PilotError("response_schema")
            if total_pages > MAX_PAGES:
                raise PilotError("page_limit")
            if total > MAX_RECORDS:
                raise PilotError("record_limit")
            if expected_total is None:
                expected_total, expected_pages = total, total_pages
            elif (total, total_pages) != (expected_total, expected_pages):
                raise PilotError("pagination_changed")
            rows = self._rows(response, seen)
            result.extend(rows)
            if len(result) > total or (page < total_pages and not rows):
                raise PilotError("response_schema")
            if page >= total_pages:
                if len(result) != total:
                    raise PilotError("pagination_incomplete")
                return result
        raise PilotError("page_limit")

    def accounts(self, item_id):
        item_id = _uuid(item_id)
        rows = self._pages("/accounts", {"itemId": item_id, "type": "CREDIT"})
        cards = []
        for row in rows:
            if _uuid(row.get("itemId")) != item_id or row.get("type") != "CREDIT":
                raise PilotError("foreign_record")
            if row.get("subtype") == "CREDIT_CARD":
                cards.append(row)
        return cards

    def bills(self, account_id):
        account_id = _uuid(account_id)
        rows = self._pages("/bills", {"accountId": account_id})
        for row in rows:
            if "accountId" in row and _uuid(row["accountId"]) != account_id:
                raise PilotError("foreign_record")
        return rows

    def transactions(self, account_id, date_from, date_to):
        account_id = _uuid(account_id)
        date_from, date_to = _day(date_from), _day(date_to)
        if date_from > date_to:
            raise PilotError("date_range")
        self.authenticate()
        query = {"accountId": account_id, "dateFrom": date_from, "dateTo": date_to}
        path = "/v2/transactions?" + urlencode(query)
        result = []
        seen = set()
        cursors = set()
        for _ in range(MAX_PAGES):
            response = self._request("GET", path)
            for row in self._rows(response, seen):
                if _uuid(row.get("accountId")) != account_id:
                    raise PilotError("foreign_record")
                result.append(row)
            if "next" not in response:
                raise PilotError("response_schema")
            next_query = response["next"]
            if next_query is None:
                return result
            query = self._cursor(next_query, query, cursors)
            path = "/v2/transactions?" + urlencode(query)
        raise PilotError("page_limit")

    @staticmethod
    def _cursor(next_query, query, seen):
        if (not isinstance(next_query, str) or len(next_query) > 4096
                or not next_query.startswith("?") or "#" in next_query
                or any(ord(char) < 33 or ord(char) > 126 for char in next_query)):
            raise PilotError("pagination_cursor")
        try:
            pairs = parse_qsl(
                next_query[1:], keep_blank_values=True, strict_parsing=True,
                max_num_fields=4,
            )
        except ValueError:
            raise PilotError("pagination_cursor") from None
        fields = dict(pairs)
        if len(fields) != len(pairs) or not set(fields) <= {
            "accountId", "dateFrom", "dateTo", "after",
        }:
            raise PilotError("pagination_cursor")
        if fields.get("accountId") != query["accountId"]:
            raise PilotError("foreign_record")
        # Provider cursors may omit date filters. Reapply the original bounds;
        # if the response supplies them, they must remain exactly unchanged.
        for key in ("dateFrom", "dateTo"):
            if key in fields and fields[key] != query[key]:
                raise PilotError("pagination_cursor")
        cursor = fields.get("after")
        if (not cursor or len(cursor) > 2048
                or any(ord(char) < 33 or ord(char) > 126 for char in cursor)):
            raise PilotError("pagination_cursor")
        if cursor in seen:
            raise PilotError("pagination_repeated")
        seen.add(cursor)
        return {**query, "after": cursor}
