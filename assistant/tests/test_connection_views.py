# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from contextlib import ExitStack
from datetime import timedelta
from html.parser import HTMLParser
import logging
from pathlib import Path
import tempfile
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from django.conf import settings
from django.db import DatabaseError
from django.test import Client, SimpleTestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from assistant.connections import oauth, service
from assistant.connections.logging import OAuthRedactionFilter
from assistant.connections.vault import CredentialVault
from assistant.models import AuthorizationAttempt, ProviderConnection
from assistant.tests.support import make_owner


class RenderedForms(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.forms = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == 'form':
            attributes = dict(attrs)
            self.forms[attributes.get('action')] = attributes


class ConnectionSettingsViewTests(TransactionTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.private = Path(self.temp.name) / 'vault'
        self.override = override_settings(ASSISTANT_PRIVATE_DIR=self.private, ASSISTANT_OPENAI_AUTH_ENABLED=False)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.user = make_owner('connection-owner')
        self.other = make_owner('connection-other')
        self.client.force_login(self.user)
        no_network = patch.object(oauth.HTTPTransport, '__call__', side_effect=AssertionError('No real OAuth'))
        no_network.start()
        self.addCleanup(no_network.stop)

    def authorization_attempt(self, owner=None, session_key=None):
        owner = owner or self.user
        return AuthorizationAttempt.objects.create(
            user=owner, session_digest=service._session_digest(owner, session_key or self.client.session.session_key),
            state_digest=service._state_digest('synthetic-state-' + uuid4().hex),
            expires_at=timezone.now() + timedelta(minutes=5), consumed_at=timezone.now(),
            status=AuthorizationAttempt.Status.VERIFIED,
        )

    def action_urls(self):
        connection = ProviderConnection.objects.create(
            user=self.user, issuer=oauth.ISSUER, subject='synthetic-subject', client_id='oaiapp_owned')
        attempt = self.authorization_attempt()
        return [
            reverse('assistant:connection-start'),
            reverse('assistant:connection-authorize', args=[connection.pk]),
            reverse('assistant:connection-activate', args=[connection.pk]),
            reverse('assistant:connection-disconnect', args=[connection.pk]),
            reverse('assistant:connection-finish', args=[attempt.pk]),
            reverse('assistant:connection-cancel', args=[attempt.pk]),
        ]

    def test_settings_are_private_local_and_do_not_initialize_credentials(self):
        for language in ['en', 'pt-br']:
            response = self.client.get(reverse('assistant:connections'), HTTP_ACCEPT_LANGUAGE=language)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'disabled')
            self.assertEqual(response['Referrer-Policy'], 'same-origin')
            self.assertIn('no-store', response['Cache-Control'])
            self.assertFalse(self.private.exists())
        self.assertEqual(ProviderConnection.objects.count(), 0)

    def test_authorization_form_csp_is_exact_and_other_routes_preserve_global_policy(self):
        def directives(response):
            return {name: values for name, *values in
                    (part.strip().split() for part in response['Content-Security-Policy'].split(';') if part.strip())}

        global_policy = {name: [str(value) for value in values] for name, values in settings.SECURE_CSP.items()}
        response = self.client.get(reverse('assistant:connections'))
        self.assertEqual(directives(response), {
            **global_policy, 'form-action': ["'self'", oauth.AUTHORIZATION_ENDPOINT],
        })
        self.assertEqual(global_policy['form-action'], ["'self'"])
        for path in [reverse('assistant:connection-callback-result'),
                     reverse('transactions:list'), reverse('accounts:settings')]:
            with self.subTest(path=path):
                default = self.client.get(path)
                self.assertEqual(default.status_code, 200)
                self.assertEqual(directives(default), global_policy)
        # The callback redirect itself must never acquire the authorization exception.
        with patch.object(service, 'receive_callback', side_effect=service.ConnectionError('state_invalid')):
            callback = self.client.get(reverse('assistant:connection-callback'), {'state': 'synthetic-state'})
        self.assertEqual(callback.status_code, 302)
        self.assertEqual(directives(callback), global_policy)
        self.assertFalse(self.private.exists())

    def test_disabled_start_never_contacts_oauth_or_creates_attempt(self):
        with patch('assistant.connections.service.oauth.new_attempt') as authorize:
            response = self.client.post(reverse('assistant:connection-start'), follow=True)
        self.assertContains(response, 'Real sign-in is disabled')
        authorize.assert_not_called()
        self.assertFalse(self.private.exists())
        self.assertEqual(AuthorizationAttempt.objects.count(), 0)

    def test_settings_and_actions_require_authentication_and_csrf(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('assistant:connections')).status_code, 302)
        self.assertEqual(self.client.post(reverse('assistant:connection-start')).status_code, 302)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        self.assertEqual(strict.post(reverse('assistant:connection-start')).status_code, 403)

    def test_foreign_records_are_not_listed_or_mutable(self):
        connection = ProviderConnection.objects.create(user=self.other, issuer='https://auth.openai.com',
            subject='private-subject', client_id='oaiapp_other', email='other@example.test')
        response = self.client.get(reverse('assistant:connections'))
        self.assertNotContains(response, 'other@example.test')
        for name in ['connection-authorize', 'connection-activate', 'connection-disconnect']:
            self.assertEqual(self.client.post(reverse('assistant:' + name, args=[connection.pk])).status_code, 404)

    def test_metadata_is_escaped_and_composer_stays_unavailable(self):
        ProviderConnection.objects.create(user=self.user, issuer='https://auth.openai.com',
            subject='<img src=x onerror=alert(1)>', client_id='oaiapp_owned',
            scopes=['chatgpt.tokens.use.direct', 'resource.invoke'], status='ready', is_active=True)
        response = self.client.get(reverse('assistant:connections'))
        self.assertContains(response, '&lt;img')
        self.assertNotContains(response, '<img src=x')
        self.assertContains(response, 'AI responses remain unavailable')
        from assistant.providers import get_provider
        from assistant.providers.base import DisconnectedProvider
        self.assertIsInstance(get_provider(), DisconnectedProvider)

    @override_settings(ASSISTANT_OPENAI_AUTH_ENABLED=True)
    def test_native_authorization_forms_preserve_original_settings_tab_without_javascript(self):
        connection = ProviderConnection.objects.create(
            user=self.user, issuer=oauth.ISSUER, subject='synthetic-subject', client_id='oaiapp_owned')
        response = self.client.get(reverse('assistant:connections'), HTTP_ACCEPT_LANGUAGE='en')
        forms = RenderedForms(response.content.decode()).forms
        for action in [reverse('assistant:connection-start'),
                       reverse('assistant:connection-authorize', args=[connection.pk])]:
            with self.subTest(action=action):
                form = forms[action]
                self.assertEqual(form['method'], 'post')
                self.assertEqual(form['target'], '_blank')
                self.assertEqual(set(form['rel'].split()), {'noopener'})
                self.assertEqual(form['hx-boost'], 'false')
        self.assertContains(response, 'Sign-in opens in a new tab.')
        self.assertFalse(self.private.exists())

    def test_same_email_registrations_have_distinct_visible_identifiers_in_cards_and_confirmation(self):
        email = 'same-email@example.test'
        connections = [ProviderConnection.objects.create(
            user=self.user, issuer=oauth.ISSUER, subject='same-subject', email=email, client_id=client_id)
            for client_id in ['oaiapp_registration_one', 'oaiapp_registration_two']]
        attempt = self.authorization_attempt()
        preview = {'email': email, 'issuer': oauth.ISSUER, 'subject': 'same-subject',
                   'client_id': 'oaiapp_pending_registration', 'scopes': ['openid', 'email']}
        with patch.object(service, 'authorization_preview', return_value=preview) as read_preview:
            response = self.client.get(reverse('assistant:connections'), HTTP_ACCEPT_LANGUAGE='en')
        read_preview.assert_called_once_with(self.user, self.client.session.session_key, attempt.pk)
        self.assertContains(response, email, count=3)
        for client_id in [connection.client_id for connection in connections] + [preview['client_id']]:
            self.assertContains(response, 'Registration: <code>' + client_id + '</code>', count=1)
        for connection in connections:
            self.assertContains(response, reverse('assistant:connection-authorize', args=[connection.pk]))
        self.assertContains(response, reverse('assistant:connection-finish', args=[attempt.pk]))
        self.assertFalse(self.private.exists())

    def test_callback_cleans_query_and_does_not_link_an_account(self):
        response = self.client.get(reverse('assistant:connection-callback'), {
            'code': 'SECRET-CODE', 'state': 'SECRET-STATE', 'client_id': 'oaiapp_test',
        })
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('SECRET', response['Location'])
        self.assertEqual(response['Referrer-Policy'], 'no-referrer')
        self.assertEqual(ProviderConnection.objects.count(), 0)

    def test_callback_duplicate_parameters_are_rejected_before_service(self):
        with patch('assistant.connection_views.service.receive_callback') as callback:
            response = self.client.get(reverse('assistant:connection-callback') + '?state=one&state=two&code=secret')
        callback.assert_not_called()
        self.assertTrue(response['Location'].endswith('status=failed'))

    @override_settings(DEBUG=True, DATA_UPLOAD_MAX_NUMBER_FIELDS=1)
    def test_oversized_callback_query_cleans_url_before_debug_rendering_or_service(self):
        anonymous = Client(raise_request_exception=False)
        code, state = 'SECRET-PARSER-CODE', 'SECRET-PARSER-STATE'
        with patch.object(service, 'receive_callback') as receive:
            response = anonymous.get(reverse('assistant:connection-callback'), {'code': code, 'state': state})
        receive.assert_not_called()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('assistant:connection-callback-result') + '?status=failed')
        self.assertEqual(response['Referrer-Policy'], 'no-referrer')
        self.assertIn('no-store', response['Cache-Control'])
        rendered = anonymous.get(response['Location'])
        self.assertEqual(rendered.status_code, 200)
        for secret in [code, state]:
            self.assertNotContains(response, secret, status_code=302)
            self.assertNotIn(secret, response['Location'])
            self.assertNotContains(rendered, secret)
        self.assertNotContains(rendered, 'Traceback')
        self.assertFalse(self.private.exists())

    @override_settings(ASSISTANT_OPENAI_AUTH_ENABLED=True)
    def test_enabled_start_uses_current_owner_session_and_native_authorization_redirect(self):
        selected = ProviderConnection.objects.create(
            user=self.user, issuer=oauth.ISSUER, subject='synthetic-subject', client_id='oaiapp_owned')
        destination = oauth.AUTHORIZATION_ENDPOINT + '?state=synthetic-state&client_id=oaiapp_owned'
        for name, args, expected_id in [('connection-start', [], None),
                                        ('connection-authorize', [selected.pk], selected.pk)]:
            with self.subTest(name=name), patch.object(service, 'begin_authorization',
                                                       return_value=(None, destination)) as begin:
                response = self.client.post(reverse('assistant:' + name, args=args), {
                    'user': self.other.pk, 'session_key': 'forged-session', 'connection_id': str(uuid4()),
                })
            begin.assert_called_once_with(self.user, self.client.session.session_key, expected_id)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response['Location'], destination)
            self.assertEqual(response['Referrer-Policy'], 'no-referrer')
            self.assertIn('no-store', response['Cache-Control'])
        self.assertFalse(self.private.exists())
        self.assertEqual(AuthorizationAttempt.objects.count(), 0)

    def test_anonymous_verified_callback_is_a_handoff_and_never_finalizes(self):
        attempt = self.authorization_attempt()
        anonymous = Client()
        params = {'state': 'synthetic-state', 'code': 'SECRET-HTTP-CODE', 'client_id': 'oaiapp_owned'}
        with patch.object(service, 'receive_callback', return_value=attempt) as receive, \
                patch.object(service, 'finish_authorization') as finish:
            response = anonymous.get(reverse('assistant:connection-callback'), params)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response['Location'], reverse('assistant:connection-callback-result') + '?status=received')
            receive.assert_called_once_with(params)
            finish.assert_not_called()
            self.assertNotIn('SECRET', response['Location'])
            self.assertEqual(response['Referrer-Policy'], 'no-referrer')
            self.assertIn('no-store', response['Cache-Control'])
            result = anonymous.get(response['Location'])
            self.assertEqual(result.status_code, 200)
            self.assertNotContains(result, 'SECRET-HTTP-CODE')
            # Completing the handoff still needs the authenticated application session.
            denied = anonymous.post(reverse('assistant:connection-finish', args=[attempt.pk]))
            self.assertEqual(denied.status_code, 302)
            self.assertIn('/accounts/login/', denied['Location'])
            finish.assert_not_called()
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, AuthorizationAttempt.Status.VERIFIED)
        self.assertEqual(ProviderConnection.objects.count(), 0)
        self.assertFalse(self.private.exists())

    def test_finish_passes_only_authenticated_current_session_and_route_attempt(self):
        attempt = self.authorization_attempt()
        with patch.object(service, 'finish_authorization') as finish:
            response = self.client.post(reverse('assistant:connection-finish', args=[attempt.pk]), {
                'user': self.other.pk, 'session_key': 'forged-session', 'attempt_id': str(uuid4()),
            })
        finish.assert_called_once_with(self.user, self.client.session.session_key, attempt.pk)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('assistant:connections'))
        self.assertIn('no-store', response['Cache-Control'])

    @override_settings(ASSISTANT_OPENAI_AUTH_ENABLED=True)
    def test_another_authenticated_session_cannot_finish_original_attempt(self):
        attempt = self.authorization_attempt()
        other_session = Client()
        other_session.force_login(self.user)
        self.assertNotEqual(other_session.session.session_key, self.client.session.session_key)
        response = other_session.post(reverse('assistant:connection-finish', args=[attempt.pk]), {
            'session_key': self.client.session.session_key,
        }, follow=True)
        self.assertContains(response, 'This authorization is unavailable')
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, AuthorizationAttempt.Status.VERIFIED)
        self.assertEqual(ProviderConnection.objects.count(), 0)
        self.assertFalse(self.private.exists())

    def test_connection_writes_are_post_only_and_reject_missing_csrf_before_service(self):
        urls = self.action_urls()
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        with ExitStack() as stack:
            actions = [stack.enter_context(patch.object(service, name)) for name in (
                'begin_authorization', 'finish_authorization', 'cancel_authorization',
                'activate_connection', 'disconnect_connection')]
            for url in urls:
                with self.subTest(url=url):
                    wrong_method = self.client.get(url)
                    self.assertEqual(wrong_method.status_code, 405)
                    self.assertEqual(wrong_method['Allow'], 'POST')
                    self.assertEqual(strict.post(url).status_code, 403)
            for action in actions:
                action.assert_not_called()
        self.assertFalse(self.private.exists())

    def test_foreign_attempt_ids_never_reach_finish_or_cancel_service(self):
        attempt = self.authorization_attempt(owner=self.other)
        with patch.object(service, 'finish_authorization') as finish, \
                patch.object(service, 'cancel_authorization') as cancel:
            for name in ['connection-finish', 'connection-cancel']:
                response = self.client.post(reverse('assistant:' + name, args=[attempt.pk]))
                self.assertEqual(response.status_code, 404)
            finish.assert_not_called()
            cancel.assert_not_called()
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, AuthorizationAttempt.Status.VERIFIED)
        self.assertFalse(self.private.exists())

    def test_valid_csrf_submission_keeps_current_authenticated_session(self):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        attempt = self.authorization_attempt(session_key=strict.session.session_key)
        self.assertEqual(strict.get(reverse('assistant:connections')).status_code, 200)
        csrf = strict.cookies['csrftoken'].value
        with patch.object(service, 'finish_authorization') as finish:
            response = strict.post(reverse('assistant:connection-finish', args=[attempt.pk]),
                                   HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(response.status_code, 302)
        finish.assert_called_once_with(self.user, strict.session.session_key, attempt.pk)

    @override_settings(ASSISTANT_OPENAI_AUTH_ENABLED=True)
    def test_authorization_csrf_accepts_same_origin_and_rejects_null_even_with_valid_token(self):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        settings_page = strict.get(reverse('assistant:connections'))
        self.assertEqual(settings_page['Referrer-Policy'], 'same-origin')
        csrf = strict.cookies['csrftoken'].value
        destination = oauth.AUTHORIZATION_ENDPOINT + '?state=synthetic-state'
        with patch.object(service, 'begin_authorization', return_value=(None, destination)) as begin:
            rejected = strict.post(reverse('assistant:connection-start'),
                                   HTTP_X_CSRFTOKEN=csrf, HTTP_ORIGIN='null')
            self.assertEqual(rejected.status_code, 403)
            begin.assert_not_called()
            accepted = strict.post(reverse('assistant:connection-start'),
                                   HTTP_X_CSRFTOKEN=csrf, HTTP_ORIGIN='http://testserver')
        self.assertEqual(accepted.status_code, 302)
        self.assertEqual(accepted['Location'], destination)
        self.assertEqual(accepted['Referrer-Policy'], 'no-referrer')
        begin.assert_called_once_with(self.user, strict.session.session_key, None)
        self.assertFalse(self.private.exists())

    @override_settings(DEBUG=True, ASSISTANT_OPENAI_AUTH_ENABLED=True)
    def test_debug_callback_raw_credential_failures_use_real_safe_service_boundary(self):
        anonymous = Client(raise_request_exception=False)
        for exception_type in [DatabaseError, RuntimeError]:
            with self.subTest(exception_type=exception_type):
                attempt, destination = service.begin_authorization(self.user, self.client.session.session_key)
                state = parse_qs(urlsplit(destination).query)['state'][0]
                secret = 'SECRET-HTTP-REFRESH-TOKEN-' + exception_type.__name__
                credentials = {
                    'issuer': oauth.ISSUER, 'subject': 'synthetic-subject', 'client_id': 'oaiapp_owned',
                    'email': 'synthetic@example.test', 'host_id': CredentialVault().host_id(),
                    'scopes': ['openid'], 'expires_at': (timezone.now() + timedelta(hours=1)).isoformat(),
                    'access_token': secret, 'refresh_token': secret, 'id_token': secret,
                }
                with patch.object(oauth, 'exchange_code', return_value=credentials) as exchange, \
                        patch.object(service, '_validate_credentials',
                                     side_effect=exception_type('refresh_token=' + secret)) as validate, \
                        patch.object(service, 'finish_authorization') as finish:
                    response = anonymous.get(reverse('assistant:connection-callback'), {
                        'state': state, 'code': 'SECRET-HTTP-AUTHORIZATION-CODE', 'client_id': 'oaiapp_owned',
                    }, follow=True)
                exchange.assert_called_once()
                validate.assert_called_once()
                finish.assert_not_called()
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.redirect_chain, [
                    (reverse('assistant:connection-callback-result') + '?status=failed', 302)])
                self.assertNotContains(response, secret)
                self.assertNotContains(response, 'SECRET-HTTP-AUTHORIZATION-CODE')
                self.assertNotContains(response, 'Traceback')
                self.assertNotIn(secret, repr(dict(response.headers)))
                attempt.refresh_from_db()
                self.assertNotEqual(attempt.status, AuthorizationAttempt.Status.VERIFIED)
        self.assertEqual(ProviderConnection.objects.count(), 0)


class OAuthLogRedactionTests(SimpleTestCase):
    def test_request_query_hints_bearer_and_exception_are_redacted(self):
        messages = [
            '"GET /assistant/connections/callback/?code=SECRET&state=STATE HTTP/1.1" 302',
            'https://auth.openai.com/api/accounts/authorize?id_token_hint=SECRET&login_hint=PRIVATE',
            'Authorization: Bearer SECRET',
            '{"refresh_token": "SECRET", "access_token": "PRIVATE"}',
        ]
        for message in messages:
            with self.subTest(message=message):
                record = logging.LogRecord('django.server', logging.INFO, __file__, 1, '%s', (message,), None)
                self.assertTrue(OAuthRedactionFilter().filter(record))
                self.assertNotIn('SECRET', record.getMessage())
                self.assertNotIn('PRIVATE', record.getMessage())
        try:
            raise ValueError('refresh_token=SECRET')
        except ValueError:
            import sys
            record = logging.LogRecord('django.request', logging.ERROR, __file__, 1, 'request failed', (), sys.exc_info())
            OAuthRedactionFilter().filter(record)
            self.assertNotIn('SECRET', record.exc_text)
