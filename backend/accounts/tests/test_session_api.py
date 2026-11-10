import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings

PASSWORD = "a-long-test-passphrase-42"


class SessionApiTestCase(TestCase):
    """Base with a JSON client that enforces CSRF like a browser session."""

    def setUp(self):
        cache.clear()  # The sign-in throttle counts requests in the cache.
        self.client = Client(enforce_csrf_checks=True)
        self.user = get_user_model().objects.create_user("ana", "ana@example.test", PASSWORD)

    def csrf(self):
        self.client.get("/api/session")
        return self.client.cookies["csrftoken"].value

    def post(self, path, payload=None, csrf=True, method="post"):
        headers = {"X-CSRFToken": self.csrf()} if csrf else {}
        return getattr(self.client, method)(
            path, data=json.dumps(payload or {}), content_type="application/json", headers=headers
        )

    def sign_in(self, username="ana", password=PASSWORD):
        return self.post("/api/session/login", {"username": username, "password": password})


class ReadSessionTests(SessionApiTestCase):
    def test_anonymous_session_has_no_user_and_sets_the_csrf_cookie(self):
        response = self.client.get("/api/session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"user": None, "preferences": None, "allow_signups": True}
        )
        self.assertIn("csrftoken", response.cookies)

    def test_signed_in_session_returns_the_user_and_default_preferences(self):
        self.sign_in()
        body = self.client.get("/api/session").json()
        self.assertEqual(body["user"], {"username": "ana", "email": "ana@example.test"})
        self.assertEqual(body["preferences"], {"base_currency": "BRL", "date_format": "DMY"})


class SignInTests(SessionApiTestCase):
    def test_correct_credentials_open_a_session(self):
        response = self.sign_in()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["username"], "ana")

    def test_wrong_password_and_unknown_user_get_the_same_answer(self):
        wrong = self.sign_in(password="not-the-password")
        unknown = self.sign_in(username="nobody")
        self.assertEqual(wrong.status_code, 400)
        self.assertEqual(wrong.json(), unknown.json())
        self.assertIsNone(self.client.get("/api/session").json()["user"])

    def test_sign_in_without_a_csrf_token_is_refused(self):
        response = self.post(
            "/api/session/login", {"username": "ana", "password": PASSWORD}, csrf=False
        )
        self.assertEqual(response.status_code, 403)

    def test_missing_field_is_reported_by_name(self):
        response = self.post("/api/session/login", {"username": "ana"})
        self.assertEqual(response.status_code, 422)
        self.assertIn("password", response.json()["errors"])

    def test_sign_in_is_throttled(self):
        for _ in range(10):
            self.sign_in(password="not-the-password")
        self.assertEqual(self.sign_in().status_code, 429)


class SignOutTests(SessionApiTestCase):
    def test_sign_out_ends_the_session(self):
        self.sign_in()
        self.assertEqual(self.post("/api/session/logout").status_code, 204)
        self.assertIsNone(self.client.get("/api/session").json()["user"])

    def test_sign_out_needs_a_session(self):
        self.assertEqual(self.post("/api/session/logout").status_code, 401)

    def test_sign_out_without_a_csrf_token_is_refused(self):
        self.sign_in()
        self.assertEqual(self.post("/api/session/logout", csrf=False).status_code, 403)
        self.assertIsNotNone(self.client.get("/api/session").json()["user"])


class SignUpTests(SessionApiTestCase):
    new_user = {"username": "bia", "email": "bia@example.test", "password": PASSWORD}

    def test_sign_up_creates_the_user_and_opens_a_session(self):
        response = self.post("/api/session/signup", self.new_user)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["username"], "bia")
        self.assertTrue(get_user_model().objects.get(username="bia").check_password(PASSWORD))

    def test_weak_password_and_taken_username_are_field_errors(self):
        response = self.post(
            "/api/session/signup", {"username": "ana", "email": "", "password": "12345"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()["errors"]), {"username", "email", "password"})
        self.assertEqual(get_user_model().objects.count(), 1)

    @override_settings(ALLOW_SIGNUPS=False)
    def test_closed_registration_refuses_sign_up(self):
        response = self.post("/api/session/signup", self.new_user)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(get_user_model().objects.filter(username="bia").exists())
        self.assertFalse(self.client.get("/api/session").json()["allow_signups"])


class PreferencesTests(SessionApiTestCase):
    def test_owner_changes_one_preference_and_keeps_the_other(self):
        self.sign_in()
        response = self.post("/api/session/preferences", {"base_currency": "USD"}, method="patch")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"base_currency": "USD", "date_format": "DMY"})

    def test_unsupported_currency_is_refused(self):
        self.sign_in()
        response = self.post("/api/session/preferences", {"base_currency": "XXX"}, method="patch")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.user.preferences.base_currency, "BRL")

    def test_preferences_need_a_session(self):
        response = self.post("/api/session/preferences", {"base_currency": "USD"}, method="patch")
        self.assertEqual(response.status_code, 401)
