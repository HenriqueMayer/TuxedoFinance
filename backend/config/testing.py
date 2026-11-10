"""Shared base for API tests."""

import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase

PASSWORD = "a-long-test-passphrase-42"


class ApiTestCase(TestCase):
    """A JSON client that enforces CSRF, as a browser session does.

    ``self.user`` is signed in unless ``signed_in`` is False. ``self.other`` is
    a second user, for ownership tests.
    """

    signed_in = True

    def setUp(self):
        cache.clear()  # The sign-in throttle counts requests in the cache.
        self.client = Client(enforce_csrf_checks=True)
        users = get_user_model().objects
        self.user = users.create_user("ana", "ana@example.test", PASSWORD)
        self.other = users.create_user("bia", "bia@example.test", PASSWORD)
        if self.signed_in:
            self.client.force_login(self.user)

    def csrf(self):
        self.client.get("/api/session")
        return self.client.cookies["csrftoken"].value

    def send(self, method, path, payload=None, *, csrf=True):
        headers = {"X-CSRFToken": self.csrf()} if csrf else {}
        return getattr(self.client, method)(
            path, data=json.dumps(payload or {}), content_type="application/json", headers=headers
        )

    def post(self, path, payload=None, **options):
        return self.send("post", path, payload, **options)

    def put(self, path, payload=None, **options):
        return self.send("put", path, payload, **options)

    def patch(self, path, payload=None, **options):
        return self.send("patch", path, payload, **options)

    def delete(self, path, **options):
        return self.send("delete", path, **options)

    def get(self, path, **query):
        return self.client.get(path, query)

    def assert_errors(self, response, status, *fields):
        """Assert an error response that names exactly ``fields``."""
        self.assertEqual(response.status_code, status, response.content)
        self.assertEqual(set(response.json().get("errors", {})), set(fields), response.content)
