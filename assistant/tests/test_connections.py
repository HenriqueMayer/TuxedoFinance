# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Synthetic OAuth lifecycle coverage; no socket or installation vault access."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import DatabaseError, IntegrityError, close_old_connections, connection, transaction
from django.test import TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from assistant.connections import oauth, service
from assistant.connections.vault import CredentialVault, VaultError
from assistant.models import AuthorizationAttempt, ProviderConnection
from assistant.tests.support import make_finances
from banking.models import BankAccount, BankMovement
from transactions.models import Transaction


@override_settings(ASSISTANT_OPENAI_AUTH_ENABLED=True,
                   ASSISTANT_OPENAI_CALLBACK_URL='http://127.0.0.1:8000/assistant/connections/callback/')
class ConnectionLifecycleTests(TransactionTestCase):
    def setUp(self):
        self.private = TemporaryDirectory(prefix='tuxedo-oauth-lifecycle.')
        self.addCleanup(self.private.cleanup)
        self.settings_override = override_settings(ASSISTANT_PRIVATE_DIR=Path(self.private.name) / 'private')
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.user = get_user_model().objects.create_user(username='oauth-owner')
        self.other = get_user_model().objects.create_user(username='oauth-other')
        self.session = 'initiating-session'
        self.vault = CredentialVault()
        self.vault.initialize()
        # A broken mock must fail before opening an outbound connection.
        self.no_network = patch.object(oauth.HTTPTransport, '__call__', side_effect=AssertionError('No real OAuth'))
        self.no_network.start()
        self.addCleanup(self.no_network.stop)

    def credentials(self, subject='subject-1', **overrides):
        result = {
            'issuer': oauth.ISSUER, 'subject': subject, 'client_id': 'issued-client-1',
            'email': f'{subject}@example.invalid', 'host_id': self.vault.host_id(),
            'scopes': ['openid', 'email', 'offline_access', 'chatgpt.tokens.use.direct', 'resource.invoke'],
            'expires_at': (timezone.now() + timedelta(hours=1)).isoformat(),
            'access_token': 'synthetic-access-secret', 'refresh_token': 'synthetic-refresh-secret',
            'id_token': 'synthetic-id-secret', 'capability': 'plan_authorized',
        }
        result.update(overrides)
        return result

    def begin(self, **kwargs):
        attempt, url = service.begin_authorization(self.user, self.session, **kwargs)
        state = parse_qs(urlsplit(url).query)['state'][0]
        return attempt, state

    def verify(self, credentials=None, **kwargs):
        attempt, state = self.begin(**kwargs)
        with patch.object(oauth, 'exchange_code', return_value=credentials or self.credentials()):
            service.receive_callback({'state': state, 'code': 'synthetic-code'})
        attempt.refresh_from_db()
        return attempt

    def connected(self, credentials=None):
        attempt = self.verify(credentials)
        return service.finish_authorization(self.user, self.session, attempt.pk)

    def expire(self, item):
        expired = timezone.now() - timedelta(seconds=1)
        ProviderConnection.objects.filter(pk=item.pk).update(expires_at=expired)
        credentials = self.vault.read(item.pk)
        credentials['expires_at'] = expired.isoformat()
        self.vault.write(item.pk, credentials)

    def assertCode(self, code, function, *args, **kwargs):
        with self.assertRaises(service.ConnectionError) as raised:
            function(*args, **kwargs)
        self.assertEqual(raised.exception.code, code)
        self.assertEqual(str(raised.exception), code)

    def test_disabled_gate_rejects_start_callback_and_refresh_even_with_mock_transport(self):
        item = self.connected()
        with override_settings(ASSISTANT_OPENAI_AUTH_ENABLED=False):
            for function, args in [
                (service.begin_authorization, (self.user, self.session)),
                (service.receive_callback, ({'state': 'state'},)),
                (service.refresh_connection, (self.user, item.pk)),
            ]:
                self.assertCode('disabled', function, *args, transport=lambda *_: None)

    def test_caller_transaction_is_rejected_before_any_vault_or_network_wait(self):
        item = self.connected()
        attempt, state = self.begin()
        operations = [
            (service.begin_authorization, (self.user, self.session)),
            (service.receive_callback, ({'state': state, 'code': 'code'},)),
            (service.finish_authorization, (self.user, self.session, attempt.pk)),
            (service.cancel_authorization, (self.user, self.session, attempt.pk)),
            (service.refresh_connection, (self.user, item.pk)),
            (service.activate_connection, (self.user, item.pk)),
            (service.disconnect_connection, (self.user, item.pk)),
        ]
        with transaction.atomic(), patch.object(CredentialVault, 'initialize') as initialize:
            for function, args in operations:
                self.assertCode('transaction_active', function, *args)
            initialize.assert_not_called()

    def test_anonymous_inactive_missing_session_and_unowned_connection_rejected(self):
        item = self.connected()
        self.assertCode('forbidden', service.begin_authorization, AnonymousUser(), self.session)
        self.assertCode('invalid_session', service.begin_authorization, self.user, None)
        self.assertCode('not_found', service.begin_authorization, self.other, self.session, connection_id=item.pk)
        for function in (service.activate_connection, service.refresh_connection, service.disconnect_connection):
            self.assertCode('not_found', function, self.other, item.pk)
            self.assertCode('not_found', function, self.user, 'not-a-uuid')
        self.user.is_active = False
        self.assertCode('forbidden', service.begin_authorization, self.user, self.session)

    def test_pending_secrets_are_encrypted_and_database_contains_only_fingerprints(self):
        attempt, state = self.begin()
        pending = self.vault.read(attempt.vault_id)['attempt']
        stored = repr(AuthorizationAttempt.objects.values().get(pk=attempt.pk))
        for secret in (self.session, state, pending['nonce'], pending['code_verifier']):
            self.assertNotIn(secret, stored)
            self.assertTrue(all(secret.encode() not in path.read_bytes()
                                for path in self.vault.root.iterdir() if path.is_file()))
        self.assertEqual(attempt.status, AuthorizationAttempt.Status.PENDING)
        self.assertEqual(ProviderConnection.objects.count(), 0)

    def test_callback_waits_for_explicit_same_owner_same_session_confirmation(self):
        attempt = self.verify()
        self.assertEqual(attempt.status, AuthorizationAttempt.Status.VERIFIED)
        self.assertIsNotNone(attempt.consumed_at)
        self.assertEqual(ProviderConnection.objects.count(), 0)
        preview = service.authorization_preview(self.user, self.session, attempt.pk)
        self.assertEqual(set(preview), {'email', 'issuer', 'subject', 'client_id', 'scopes'})
        self.assertEqual(preview['email'], 'subject-1@example.invalid')
        self.assertCode('not_found', service.finish_authorization, self.other, self.session, attempt.pk)
        self.assertCode('invalid_session', service.finish_authorization, self.user, 'rotated-session', attempt.pk)
        self.assertCode('invalid_session', service.authorization_preview, self.user, 'rotated-session', attempt.pk)
        self.assertFalse(service.pending_authorizations(self.other, self.session).exists())
        self.assertFalse(service.pending_authorizations(self.user, 'rotated-session').exists())
        item = service.finish_authorization(self.user, self.session, attempt.pk)
        self.assertTrue(item.is_active)
        self.assertEqual(item.status, ProviderConnection.Status.READY)
        with self.assertRaises(VaultError):
            self.vault.read(attempt.vault_id)
        self.assertCode('attempt_used', service.finish_authorization, self.user, self.session, attempt.pk)

    def test_preview_never_initializes_private_storage_or_creates_lock_files(self):
        attempt = self.verify()
        before = {path.name: (path.stat().st_mtime_ns, path.read_bytes())
                  for path in self.vault.root.iterdir() if path.is_file()}
        with (patch.object(CredentialVault, 'initialize', side_effect=AssertionError('GET initialized vault')),
              patch.object(CredentialVault, 'lock', side_effect=AssertionError('GET created lock'))):
            self.assertEqual(service.authorization_preview(self.user, self.session, attempt.pk)['subject'], 'subject-1')
        after = {path.name: (path.stat().st_mtime_ns, path.read_bytes())
                 for path in self.vault.root.iterdir() if path.is_file()}
        self.assertEqual(before, after)

    def test_callback_replay_unknown_state_and_parallel_claim_never_repeat_exchange(self):
        attempt, state = self.begin()
        self.assertCode('state_invalid', service.receive_callback, {'state': 'unknown-state', 'code': 'bad'})
        def exchange(*args, **kwargs):
            self.assertFalse(connection.in_atomic_block)
            self.assertCode('attempt_used', service.receive_callback, {'state': state, 'code': 'second-code'})
            return self.credentials()
        with patch.object(oauth, 'exchange_code', side_effect=exchange) as mocked:
            service.receive_callback({'state': state, 'code': 'first-code'})
            self.assertCode('attempt_used', service.receive_callback, {'state': state, 'code': 'first-code'})
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(AuthorizationAttempt.objects.get(pk=attempt.pk).status, AuthorizationAttempt.Status.VERIFIED)

    def test_expiry_cleans_secrets_and_pending_cap_covers_all_browser_tabs(self):
        first, state = self.begin()
        AuthorizationAttempt.objects.filter(pk=first.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        with patch.object(oauth, 'exchange_code') as exchange:
            self.assertCode('attempt_expired', service.receive_callback, {'state': state, 'code': 'old-code'})
            exchange.assert_not_called()
        with self.assertRaises(VaultError):
            self.vault.read(first.vault_id)
        for index in range(service.MAX_PENDING_ATTEMPTS):
            service.begin_authorization(self.user, f'tab-{index}')
        self.assertCode('too_many_attempts', service.begin_authorization, self.user, 'another-tab')
        expired = AuthorizationAttempt.objects.filter(status=AuthorizationAttempt.Status.PENDING).first()
        AuthorizationAttempt.objects.filter(pk=expired.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        service.begin_authorization(self.user, 'another-tab')
        expired.refresh_from_db()
        self.assertEqual(expired.status, AuthorizationAttempt.Status.EXPIRED)
        with self.assertRaises(VaultError):
            self.vault.read(expired.vault_id)

    def test_multiple_tabs_have_independent_callbacks_and_owner_selects_one_account(self):
        first, first_state = self.begin()
        second, second_url = service.begin_authorization(self.user, 'second-tab')
        second_state = parse_qs(urlsplit(second_url).query)['state'][0]
        with patch.object(oauth, 'exchange_code', side_effect=[self.credentials('one'), self.credentials('two')]):
            service.receive_callback({'state': second_state, 'code': 'second'})
            service.receive_callback({'state': first_state, 'code': 'first'})
        self.assertEqual(list(service.pending_authorizations(self.user, self.session)), [first])
        one = service.finish_authorization(self.user, self.session, first.pk)
        two = service.finish_authorization(self.user, 'second-tab', second.pk)
        one.refresh_from_db()
        self.assertFalse(one.is_active)
        self.assertTrue(two.is_active)
        service.activate_connection(self.user, one.pk)
        self.assertEqual(list(ProviderConnection.objects.filter(is_active=True)), [one])
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProviderConnection.objects.filter(pk=two.pk).update(is_active=True)

    def test_same_provider_identity_is_owned_separately_and_reauth_reuses_only_stable_identity(self):
        item = self.connected()
        other_attempt, url = service.begin_authorization(self.other, 'other-session')
        state = parse_qs(urlsplit(url).query)['state'][0]
        with patch.object(oauth, 'exchange_code', return_value=self.credentials()):
            service.receive_callback({'state': state, 'code': 'other-code'})
        other = service.finish_authorization(self.other, 'other-session', other_attempt.pk)
        self.assertNotEqual(item.pk, other.pk)
        self.assertTrue(ProviderConnection.objects.get(pk=item.pk).is_active)
        attempt, _ = self.begin(connection_id=item.pk)
        pending = self.vault.read(attempt.vault_id)['attempt']
        self.assertEqual(pending['client_id'], item.client_id)
        self.assertEqual(pending['subject'], item.subject)
        self.assertEqual(pending['host_id'], self.vault.host_id())
        self.assertNotIn('access_token', pending)
        self.assertNotIn('refresh_token', pending)

    def test_failed_or_different_identity_reauth_preserves_current_connection(self):
        item = self.connected()
        previous = self.vault.read(item.pk)
        for failure in (oauth.OAuthError('access_denied'), self.credentials('wrong-person')):
            attempt, state = self.begin(connection_id=item.pk)
            with patch.object(oauth, 'exchange_code', side_effect=failure if isinstance(failure, Exception) else None,
                              return_value=failure):
                self.assertCode('access_denied' if isinstance(failure, Exception) else 'identity_mismatch',
                                service.receive_callback, {'state': state, 'code': 'bad-reauth'})
            self.assertEqual(self.vault.read(item.pk), previous)
            item.refresh_from_db()
            self.assertEqual(item.status, ProviderConnection.Status.READY)
            self.assertTrue(item.is_active)
            self.assertEqual(AuthorizationAttempt.objects.get(pk=attempt.pk).status, AuthorizationAttempt.Status.FAILED)

    def test_identity_only_is_saved_honestly_and_does_not_select_provider(self):
        item = self.connected(self.credentials(scopes=['openid', 'email'], capability='identity_only'))
        self.assertEqual(item.status, ProviderConnection.Status.IDENTITY_ONLY)
        from assistant.providers import get_provider
        from assistant.providers.base import DisconnectedProvider
        self.assertIsInstance(get_provider(), DisconnectedProvider)
        stored = repr(ProviderConnection.objects.values().get(pk=item.pk))
        self.assertNotIn('synthetic-access-secret', stored)
        self.assertNotIn('synthetic-refresh-secret', stored)

    def test_refresh_rotation_is_serialized_and_http_runs_outside_database_transaction(self):
        item = self.connected()
        self.expire(item)
        entered, release = Event(), Event()
        rotated = self.credentials(access_token='rotated-access', refresh_token='rotated-refresh')
        def refresh(credentials, **kwargs):
            self.assertFalse(connection.in_atomic_block)
            self.assertEqual(credentials['refresh_token'], 'synthetic-refresh-secret')
            entered.set()
            self.assertTrue(release.wait(3))
            return rotated
        def worker():
            close_old_connections()
            try:
                return service.refresh_connection(self.user, item.pk).pk
            finally:
                close_old_connections()
        with patch.object(oauth, 'refresh_credentials', side_effect=refresh) as mocked:
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(worker)
                self.assertTrue(entered.wait(3))
                second = pool.submit(worker)
                release.set()
                self.assertEqual(first.result(timeout=5), item.pk)
                self.assertEqual(second.result(timeout=5), item.pk)
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(self.vault.read(item.pk)['refresh_token'], 'rotated-refresh')

    def test_transient_refresh_preserves_tokens_but_invalid_grant_clears_reusable_secrets(self):
        item = self.connected()
        self.expire(item)
        before = self.vault.read(item.pk)
        with patch.object(oauth, 'refresh_credentials', side_effect=oauth.OAuthError('network_error')):
            self.assertCode('network_error', service.refresh_connection, self.user, item.pk)
        self.assertEqual(self.vault.read(item.pk), before)
        item.refresh_from_db()
        self.assertEqual(item.status, ProviderConnection.Status.READY)
        with patch.object(oauth, 'refresh_credentials', side_effect=oauth.OAuthError('invalid_grant')):
            self.assertCode('invalid_grant', service.refresh_connection, self.user, item.pk)
        item.refresh_from_db()
        self.assertEqual(item.status, ProviderConnection.Status.RECONNECT)
        self.assertEqual(set(self.vault.read(item.pk)), {'issuer', 'subject', 'client_id', 'host_id', 'email'})

    def test_refresh_rejects_identity_replacement_and_clears_unusable_credentials(self):
        item = self.connected()
        self.expire(item)
        with patch.object(oauth, 'refresh_credentials', return_value=self.credentials('different')):
            self.assertCode('identity_mismatch', service.refresh_connection, self.user, item.pk)
        item.refresh_from_db()
        self.assertEqual(item.subject, 'subject-1')
        self.assertEqual(item.status, ProviderConnection.Status.RECONNECT)
        self.assertNotIn('refresh_token', self.vault.read(item.pk))

    def test_misassociated_vault_identity_cannot_redirect_reauth_or_revoke_another_account(self):
        item = self.connected()
        self.vault.write(item.pk, self.credentials('wrong-vault-person', client_id='wrong-client'))
        with patch.object(oauth, 'refresh_credentials') as refresh:
            self.assertCode('identity_mismatch', service.refresh_connection, self.user, item.pk)
            refresh.assert_not_called()
        registration = self.vault.read(item.pk)
        self.assertEqual(registration['subject'], item.subject)
        self.assertEqual(registration['client_id'], item.client_id)
        attempt, _ = self.begin(connection_id=item.pk)
        self.assertEqual(self.vault.read(attempt.vault_id)['attempt']['subject'], item.subject)
        self.vault.write(item.pk, self.credentials('wrong-vault-person'))
        with patch.object(oauth, 'revoke_credentials') as revoke:
            service.disconnect_connection(self.user, item.pk)
            revoke.assert_not_called()
        self.assertEqual(self.vault.read(item.pk)['subject'], item.subject)

    def test_rotated_credentials_survive_metadata_failure_without_exchanging_old_refresh_again(self):
        item = self.connected()
        self.expire(item)
        rotated = self.credentials(refresh_token='rotated-before-db-error')
        with (patch.object(oauth, 'refresh_credentials', return_value=rotated),
              patch('django.db.models.query.QuerySet.update', side_effect=DatabaseError('synthetic-secret-db-error'))):
            self.assertCode('storage_unavailable', service.refresh_connection, self.user, item.pk)
        self.assertEqual(self.vault.read(item.pk)['refresh_token'], 'rotated-before-db-error')
        with patch.object(oauth, 'refresh_credentials') as refresh:
            repaired = service.refresh_connection(self.user, item.pk)
            refresh.assert_not_called()
        self.assertGreater(repaired.expires_at, timezone.now())

    def test_failed_metadata_commit_preserves_verified_handoff_for_retry(self):
        attempt = self.verify()
        with patch.object(ProviderConnection, 'save', side_effect=DatabaseError('synthetic-secret-db-error')):
            self.assertCode('storage_unavailable', service.finish_authorization, self.user, self.session, attempt.pk)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, AuthorizationAttempt.Status.VERIFIED)
        self.assertEqual(ProviderConnection.objects.count(), 0)
        self.assertEqual(self.vault.read(attempt.vault_id)['kind'], 'verified')
        linked = service.finish_authorization(self.user, self.session, attempt.pk)
        self.assertTrue(linked.is_active)

    def test_expired_cleanup_removes_unreferenced_target_after_interrupted_insert(self):
        attempt, _ = self.begin()
        orphan_id = service._staged_connection_id(attempt)
        self.vault.write(orphan_id, self.credentials())
        AuthorizationAttempt.objects.filter(pk=attempt.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.begin()
        with self.assertRaises(VaultError):
            self.vault.read(orphan_id)

    def test_disconnect_is_local_even_when_revocation_fails_and_retains_stable_registration(self):
        item = self.connected()
        original_host = self.vault.host_id()
        def revoke(*args, **kwargs):
            self.assertFalse(connection.in_atomic_block)
            raise oauth.OAuthError('network_error')
        with patch.object(oauth, 'revoke_credentials', side_effect=revoke):
            disconnected, revoked = service.disconnect_connection(self.user, item.pk)
        self.assertFalse(revoked)
        self.assertFalse(disconnected.is_active)
        self.assertEqual(disconnected.status, ProviderConnection.Status.DISCONNECTED)
        self.assertEqual(set(self.vault.read(item.pk)), {'issuer', 'subject', 'client_id', 'host_id', 'email'})
        attempt, _ = self.begin(connection_id=item.pk)
        pending = self.vault.read(attempt.vault_id)['attempt']
        self.assertEqual(pending['client_id'], item.client_id)
        self.assertEqual(pending['host_id'], original_host)
        self.assertCode('reconnect_required', service.activate_connection, self.user, item.pk)
        self.assertCode('reconnect_required', service.refresh_connection, self.user, item.pk)

    def test_disabled_disconnect_and_cancellation_do_not_call_provider(self):
        item = self.connected()
        attempt, state = self.begin()
        with override_settings(ASSISTANT_OPENAI_AUTH_ENABLED=False), patch.object(oauth, 'revoke_credentials') as revoke:
            service.disconnect_connection(self.user, item.pk)
            cancelled = service.cancel_authorization(self.user, self.session, attempt.pk)
            revoke.assert_not_called()
        self.assertEqual(cancelled.error_code, 'authorization_cancelled')
        self.assertCode('attempt_used', service.receive_callback, {'state': state, 'code': 'late-code'})
        with self.assertRaises(VaultError):
            self.vault.read(attempt.vault_id)

    def test_cancelled_in_flight_callback_cannot_resurrect_pending_credentials(self):
        attempt, state = self.begin()
        entered, release = Event(), Event()
        def exchange(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(3))
            return self.credentials()
        def callback_worker():
            close_old_connections()
            try:
                return service.receive_callback({'state': state, 'code': 'cancelled-code'})
            finally:
                close_old_connections()
        def cancel_worker():
            close_old_connections()
            try:
                return service.cancel_authorization(self.user, self.session, attempt.pk)
            finally:
                close_old_connections()
        with patch.object(oauth, 'exchange_code', side_effect=exchange):
            with ThreadPoolExecutor(max_workers=2) as pool:
                callback = pool.submit(callback_worker)
                self.assertTrue(entered.wait(3))
                cancel = pool.submit(cancel_worker)
                # The terminal DB update happens before cancellation waits for
                # the vault lock held by the exchange. Poll no external system.
                import time
                deadline = time.monotonic() + 3
                while AuthorizationAttempt.objects.get(pk=attempt.pk).error_code != 'authorization_cancelled':
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(0.01)
                release.set()
                self.assertCode('authorization_cancelled', callback.result, timeout=5)
                self.assertEqual(cancel.result(timeout=5).status, AuthorizationAttempt.Status.FAILED)
        self.assertEqual(ProviderConnection.objects.count(), 0)
        with self.assertRaises(VaultError):
            self.vault.read(attempt.vault_id)

    def test_oauth_errors_are_static_and_financial_records_never_change(self):
        make_finances(self.user)
        before = {model: list(model.objects.values()) for model in (BankAccount, BankMovement, Transaction)}
        with CaptureQueriesContext(connection) as queries:
            item = self.connected()
            with patch.object(oauth, 'revoke_credentials', return_value=True):
                self.assertTrue(service.disconnect_connection(self.user, item.pk)[1])
        for model, values in before.items():
            self.assertEqual(list(model.objects.values()), values)
        writes = [entry['sql'] for entry in queries if entry['sql'].startswith(('INSERT', 'UPDATE', 'DELETE'))]
        for sql in writes:
            self.assertFalse(any(table in sql for table in ('banking_', 'transactions_', 'investments_', 'planning_')))
        attempt, state = self.begin()
        with patch.object(oauth, 'exchange_code', side_effect=oauth.OAuthError('secret-untrusted-provider-body')):
            self.assertCode('provider_error', service.receive_callback, {'state': state, 'code': 'secret-code'})
        attempt.refresh_from_db()
        self.assertEqual(attempt.error_code, 'provider_error')
