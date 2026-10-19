# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Account authorization lifecycle, isolated from financial data and inference."""
from datetime import timedelta
from dataclasses import dataclass, field
from functools import wraps
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connections, transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.dateparse import parse_datetime

from assistant.models import AuthorizationAttempt, ProviderConnection

from . import oauth
from .vault import CredentialVault, VaultError


ATTEMPT_LIFETIME = timedelta(minutes=10)
MAX_PENDING_ATTEMPTS = 5
_USER_LOCK_NAMESPACE = uuid.UUID('ab34ed5f-6477-41fd-b75d-c72682ef1038')
_CONNECTION_NAMESPACE = uuid.UUID('b6620d61-993f-47f9-8540-9fae363db7b0')
_OPEN_ATTEMPTS = [AuthorizationAttempt.Status.PENDING, AuthorizationAttempt.Status.EXCHANGING,
                  AuthorizationAttempt.Status.VERIFIED, AuthorizationAttempt.Status.FINISHING]
_SAFE_PROVIDER_CODES = {
    'access_denied', 'authorization_error', 'authorization_pending', 'invalid_grant',
    'invalid_request', 'invalid_scope', 'invalid_client', 'unauthorized_client',
    'unsupported_grant_type', 'temporarily_unavailable', 'server_error', 'token_error',
    'network_error', 'identity_mismatch', 'identity_invalid', 'token_invalid',
    'invalid_token', 'invalid_response', 'state_invalid', 'nonce_invalid',
    'registration_error', 'configuration_error', 'transport_error', 'provider_error',
    'callback_invalid', 'credentials_invalid', 'issuer_mismatch', 'host_mismatch',
    'invalid_state', 'client_mismatch', 'invalid_nonce', 'invalid_id_token',
    'invalid_scopes', 'auth_disabled', 'reauth_required', 'invalid_redirect',
    'invalid_host', 'invalid_registration', 'invalid_attempt', 'invalid_discovery',
    'invalid_endpoint', 'discovery_error', 'jwks_error', 'login_required',
    'interaction_required', 'consent_required',
}


class ConnectionError(Exception):
    """A stable public code, with no provider body or credential in its message."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _public_errors(function):
    @wraps(function)
    def public(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except ConnectionError:
            raise
        except VaultError:
            raise ConnectionError('vault_unavailable') from None
        except oauth.OAuthError as exc:
            raise ConnectionError(_provider_code(exc)) from None
        except DatabaseError:
            raise ConnectionError('storage_unavailable') from None
        except Exception:
            # Error responses must never expose a provider body or a traceback
            # containing PKCE/tokens, including on a local DEBUG installation.
            raise ConnectionError('connection_error') from None
    return public


def _enabled():
    if getattr(settings, 'ASSISTANT_OPENAI_AUTH_ENABLED', False) is not True:
        raise ConnectionError('disabled')


def _outside_transaction():
    if any(database.in_atomic_block for database in connections.all(initialized_only=True)):
        raise ConnectionError('transaction_active')


def _owner(user):
    if not getattr(user, 'is_authenticated', False) or not getattr(user, 'is_active', False) or not user.pk:
        raise ConnectionError('forbidden')


def _digest(value, salt):
    return salted_hmac(salt, value, algorithm='sha256').hexdigest()


def _session_digest(user, session_key):
    _owner(user)
    if not isinstance(session_key, str) or not session_key or len(session_key) > 256:
        raise ConnectionError('invalid_session')
    return _digest(f'{user.pk}:{session_key}', 'assistant.oauth.session.v1')


def _state_digest(state):
    if not isinstance(state, str) or not state or len(state) > 4096:
        raise ConnectionError('state_invalid')
    return _digest(state, 'assistant.oauth.state.v1')


def _user_lock(user):
    # A per-owner file lock serializes account selection without a database
    # transaction waiting for filesystem locks or token-endpoint requests.
    return uuid.uuid5(_USER_LOCK_NAMESPACE, str(user.pk))


def _staged_connection_id(attempt):
    return uuid.uuid5(_CONNECTION_NAMESPACE, str(attempt.pk))


def _vault():
    vault = CredentialVault()
    vault.initialize()
    return vault


def _connection(user, connection_id):
    _owner(user)
    try:
        return ProviderConnection.objects.get(pk=connection_id, user=user, provider='openai')
    except (ProviderConnection.DoesNotExist, ValueError, TypeError, ValidationError):
        raise ConnectionError('not_found') from None


def _attempt(user, session_key, attempt_id, *, allow_expired=False):
    expected = _session_digest(user, session_key)
    try:
        attempt = AuthorizationAttempt.objects.get(pk=attempt_id, user=user)
    except (AuthorizationAttempt.DoesNotExist, ValueError, TypeError, ValidationError):
        raise ConnectionError('not_found') from None
    if not constant_time_compare(attempt.session_digest, expected):
        raise ConnectionError('invalid_session')
    if not allow_expired and attempt.expires_at <= timezone.now():
        raise ConnectionError('attempt_expired')
    return attempt


def _provider_code(exc):
    return exc.code if exc.code in _SAFE_PROVIDER_CODES else 'provider_error'


def _identity(value):
    return tuple(value.get(key) for key in ('issuer', 'subject', 'client_id'))


def _validate_credentials(credentials, vault, expected=None):
    if not isinstance(credentials, dict):
        raise ConnectionError('credentials_invalid')
    for key in ('issuer', 'subject', 'client_id'):
        value = credentials.get(key)
        if not isinstance(value, str) or not value or len(value) > 255:
            raise ConnectionError('credentials_invalid')
    if credentials['issuer'] != oauth.ISSUER:
        raise ConnectionError('credentials_invalid')
    if credentials.get('host_id') != vault.host_id():
        raise ConnectionError('host_mismatch')
    scopes = credentials.get('scopes')
    if not isinstance(scopes, list) or any(not isinstance(scope, str) or len(scope) > 255 for scope in scopes):
        raise ConnectionError('credentials_invalid')
    email = credentials.get('email', '')
    if not isinstance(email, str) or len(email) > 254:
        raise ConnectionError('credentials_invalid')
    expiry = credentials.get('expires_at')
    if expiry is not None:
        if not isinstance(expiry, str):
            raise ConnectionError('credentials_invalid')
        try:
            expiry = parse_datetime(expiry)
        except ValueError:
            expiry = None
        if expiry is None or timezone.is_naive(expiry):
            raise ConnectionError('credentials_invalid')
    if expected and _identity(credentials) != (expected.issuer, expected.subject, expected.client_id):
        raise ConnectionError('identity_mismatch')
    return expiry


def _metadata(credentials, expiry):
    ready = (credentials.get('capability') == 'plan_authorized'
             and {'chatgpt.tokens.use.direct', 'resource.invoke'}.issubset(credentials['scopes'])
             and bool(credentials.get('access_token')))
    return {
        'issuer': credentials['issuer'], 'subject': credentials['subject'],
        'client_id': credentials['client_id'], 'email': credentials.get('email', ''),
        'scopes': list(credentials['scopes']), 'expires_at': expiry,
        'status': ProviderConnection.Status.READY if ready else ProviderConnection.Status.IDENTITY_ONLY,
    }


def _registration(credentials, connection, vault):
    """Keep stable registration identity while removing every reusable token."""
    expected = (connection.issuer, connection.subject, connection.client_id)
    if (isinstance(credentials, dict) and _identity(credentials) == expected
            and credentials.get('host_id') == vault.host_id()):
        return {key: credentials[key] for key in ('issuer', 'subject', 'client_id', 'host_id', 'email')
                if key in credentials}
    # A restored/misassociated vault record cannot change whose account the
    # metadata names or revoke another account's tokens during local cleanup.
    return {'issuer': connection.issuer, 'subject': connection.subject,
            'client_id': connection.client_id, 'email': connection.email, 'host_id': vault.host_id()}


def _expire_attempts(user, vault):
    for attempt in AuthorizationAttempt.objects.filter(user=user, expires_at__lte=timezone.now()):
        with vault.lock(attempt.vault_id):
            vault.delete(attempt.vault_id)
        staged_id = _staged_connection_id(attempt)
        if not ProviderConnection.objects.filter(pk=staged_id).exists():
            with vault.lock(staged_id):
                vault.delete(staged_id)
        if attempt.status != AuthorizationAttempt.Status.COMPLETE:
            AuthorizationAttempt.objects.filter(pk=attempt.pk).update(
                status=AuthorizationAttempt.Status.EXPIRED, error_code='attempt_expired', updated_at=timezone.now())


def pending_authorizations(user, session_key):
    """Only this browser session may inspect or confirm its pending handoffs."""
    digest = _session_digest(user, session_key)
    return AuthorizationAttempt.objects.filter(
        user=user, session_digest=digest, expires_at__gt=timezone.now(),
        status__in=[AuthorizationAttempt.Status.PENDING, AuthorizationAttempt.Status.VERIFIED])


@_public_errors
def authorization_preview(user, session_key, attempt_id):
    attempt = _attempt(user, session_key, attempt_id)
    if attempt.status != AuthorizationAttempt.Status.VERIFIED:
        raise ConnectionError('attempt_used')
    try:
        # Atomic ciphertext replacement makes status preview a read-only GET:
        # do not initialize the private directory or create a lock file here.
        vault = CredentialVault()
        stored = vault.read(attempt.vault_id)
        credentials = stored.get('credentials') if stored.get('kind') == 'verified' else None
        _validate_credentials(credentials, vault)
        return {key: credentials.get(key, '') for key in ('email', 'issuer', 'subject', 'client_id', 'scopes')}
    except VaultError:
        raise ConnectionError('vault_unavailable') from None


@_public_errors
def begin_authorization(user, session_key, connection_id=None, transport=None):
    _enabled()
    _outside_transaction()
    digest = _session_digest(user, session_key)
    selected = _connection(user, connection_id) if connection_id else None
    try:
        vault = _vault()
        with vault.lock(_user_lock(user)):
            _expire_attempts(user, vault)
            if AuthorizationAttempt.objects.filter(user=user, status__in=_OPEN_ATTEMPTS).count() >= MAX_PENDING_ATTEMPTS:
                raise ConnectionError('too_many_attempts')
            registration = None
            if selected:
                with vault.lock(selected.pk):
                    try:
                        registration = _registration(vault.read(selected.pk), selected, vault)
                    except VaultError as exc:
                        if exc.code != 'record_not_found':
                            raise
                if registration is None:
                    registration = {'issuer': selected.issuer, 'subject': selected.subject,
                                    'client_id': selected.client_id, 'email': selected.email,
                                    'host_id': vault.host_id()}
            pending = oauth.new_attempt(settings.ASSISTANT_OPENAI_CALLBACK_URL, vault.host_id(), registration=registration)
            url = oauth.authorization_url(pending)
            attempt = AuthorizationAttempt(user=user, session_digest=digest,
                                           state_digest=_state_digest(pending.get('state')),
                                           connection=selected, expires_at=timezone.now() + ATTEMPT_LIFETIME)
            vault.write(attempt.vault_id, {'kind': 'authorization', 'attempt': pending})
            try:
                attempt.save(force_insert=True)
            except Exception:
                vault.delete(attempt.vault_id)
                raise
        return attempt, url
    except VaultError:
        raise ConnectionError('vault_unavailable') from None
    except oauth.OAuthError as exc:
        raise ConnectionError(_provider_code(exc)) from None


@_public_errors
def receive_callback(params, transport=None):
    """Validate once without cookies; account attachment requires a later POST."""
    _enabled()
    _outside_transaction()
    if hasattr(params, 'getlist') and len(params.getlist('state')) != 1:
        raise ConnectionError('state_invalid')
    digest = _state_digest(params.get('state'))
    try:
        attempt = AuthorizationAttempt.objects.get(state_digest=digest)
    except AuthorizationAttempt.DoesNotExist:
        raise ConnectionError('state_invalid') from None
    if attempt.status != AuthorizationAttempt.Status.PENDING or attempt.consumed_at is not None:
        raise ConnectionError('attempt_used')
    now = timezone.now()
    if attempt.expires_at <= now:
        try:
            vault = _vault()
            with vault.lock(attempt.vault_id):
                vault.delete(attempt.vault_id)
        except VaultError:
            pass
        AuthorizationAttempt.objects.filter(pk=attempt.pk).update(
            status=AuthorizationAttempt.Status.EXPIRED, error_code='attempt_expired', updated_at=now)
        raise ConnectionError('attempt_expired')
    # This single conditional write claims the callback before vault I/O or HTTP.
    # An interrupted exchange fails closed; its authorization code is never reused.
    claimed = AuthorizationAttempt.objects.filter(
        pk=attempt.pk, status=AuthorizationAttempt.Status.PENDING, consumed_at__isnull=True,
        expires_at__gt=now).update(status=AuthorizationAttempt.Status.EXCHANGING, consumed_at=now, updated_at=now)
    if not claimed:
        raise ConnectionError('attempt_used')
    vault = None
    try:
        vault = _vault()
        with vault.lock(attempt.vault_id):
            stored = vault.read(attempt.vault_id)
            if stored.get('kind') != 'authorization' or not isinstance(stored.get('attempt'), dict):
                raise ConnectionError('credentials_invalid')
            pending = stored['attempt']
            credentials = oauth.exchange_code(pending, params, transport=transport)
            selected = _connection(attempt.user, attempt.connection_id) if attempt.connection_id else None
            _validate_credentials(credentials, vault, expected=selected)
            vault.write(attempt.vault_id, {'kind': 'verified', 'credentials': credentials})
            advanced = AuthorizationAttempt.objects.filter(
                pk=attempt.pk, status=AuthorizationAttempt.Status.EXCHANGING,
                expires_at__gt=timezone.now()).update(
                    status=AuthorizationAttempt.Status.VERIFIED, error_code='', updated_at=timezone.now())
            if not advanced:
                vault.delete(attempt.vault_id)
                raise ConnectionError('attempt_expired' if attempt.expires_at <= timezone.now()
                                      else 'authorization_cancelled')
        attempt.refresh_from_db()
        if attempt.status != AuthorizationAttempt.Status.VERIFIED:
            raise ConnectionError('authorization_cancelled')
        return attempt
    except (VaultError, oauth.OAuthError, ConnectionError) as exc:
        code = ('vault_unavailable' if isinstance(exc, VaultError) else
                _provider_code(exc) if isinstance(exc, oauth.OAuthError) else exc.code)
        AuthorizationAttempt.objects.filter(pk=attempt.pk, status=AuthorizationAttempt.Status.EXCHANGING).update(
            status=AuthorizationAttempt.Status.FAILED, error_code=code, updated_at=timezone.now())
        if vault is not None:
            try:
                with vault.lock(attempt.vault_id):
                    vault.delete(attempt.vault_id)
            except VaultError:
                pass
        raise ConnectionError(code) from None


@_public_errors
def cancel_authorization(user, session_key, attempt_id):
    """Invalidate first, then delete secrets even when outbound auth is disabled."""
    _outside_transaction()
    attempt = _attempt(user, session_key, attempt_id, allow_expired=True)
    changed = AuthorizationAttempt.objects.filter(pk=attempt.pk, status__in=_OPEN_ATTEMPTS).exclude(
        status=AuthorizationAttempt.Status.FINISHING).update(
            status=AuthorizationAttempt.Status.FAILED, error_code='authorization_cancelled',
            consumed_at=timezone.now(), updated_at=timezone.now())
    if not changed:
        raise ConnectionError('attempt_used')
    try:
        vault = _vault()
        with vault.lock(attempt.vault_id):
            vault.delete(attempt.vault_id)
    except VaultError:
        raise ConnectionError('vault_unavailable') from None
    attempt.refresh_from_db()
    return attempt


@_public_errors
def finish_authorization(user, session_key, attempt_id):
    _enabled()
    _outside_transaction()
    attempt = _attempt(user, session_key, attempt_id)
    try:
        vault = _vault()
        with vault.lock(_user_lock(user)):
            claimed = AuthorizationAttempt.objects.filter(
                pk=attempt.pk, status=AuthorizationAttempt.Status.VERIFIED,
                expires_at__gt=timezone.now()).update(status=AuthorizationAttempt.Status.FINISHING, updated_at=timezone.now())
            if not claimed:
                raise ConnectionError('attempt_used')
            try:
                with vault.lock(attempt.vault_id):
                    stored = vault.read(attempt.vault_id)
                    credentials = stored.get('credentials') if stored.get('kind') == 'verified' else None
                    selected = _connection(user, attempt.connection_id) if attempt.connection_id else None
                    expiry = _validate_credentials(credentials, vault, expected=selected)
                    connection = selected or ProviderConnection.objects.filter(
                        user=user, provider='openai', issuer=credentials['issuer'], subject=credentials['subject'],
                        client_id=credentials['client_id']).first()
                    # A deterministic target lets expiry cleanup find an orphan
                    # if this process exits between its vault write and DB insert.
                    connection = connection or ProviderConnection(user=user, pk=_staged_connection_id(attempt))
                    with vault.lock(connection.pk):
                        if attempt.expires_at <= timezone.now():
                            raise ConnectionError('attempt_expired')
                        try:
                            previous = vault.read(connection.pk)
                        except VaultError as exc:
                            if exc.code != 'record_not_found':
                                raise
                            previous = None
                        vault.write(connection.pk, credentials)
                        try:
                            with transaction.atomic():
                                ProviderConnection.objects.filter(user=user, is_active=True).update(is_active=False)
                                for key, value in _metadata(credentials, expiry).items():
                                    setattr(connection, key, value)
                                connection.is_active = True
                                connection.save()
                                AuthorizationAttempt.objects.filter(pk=attempt.pk).update(
                                    status=AuthorizationAttempt.Status.COMPLETE, connection=connection, updated_at=timezone.now())
                        except Exception:
                            if previous is None:
                                vault.delete(connection.pk)
                            else:
                                vault.write(connection.pk, previous)
                            raise
                    try:
                        vault.delete(attempt.vault_id)
                    except VaultError:
                        # The DB commit succeeded. Expiry/disconnect can remove
                        # this encrypted duplicate without undoing the account.
                        pass
                return connection
            except Exception:
                AuthorizationAttempt.objects.filter(pk=attempt.pk, status=AuthorizationAttempt.Status.FINISHING).update(
                    status=AuthorizationAttempt.Status.VERIFIED, updated_at=timezone.now())
                raise
    except VaultError:
        raise ConnectionError('vault_unavailable') from None


def _mark_reconnect(connection, vault, credentials):
    vault.write(connection.pk, _registration(credentials, connection, vault))
    ProviderConnection.objects.filter(pk=connection.pk, user=connection.user).update(
        status=ProviderConnection.Status.RECONNECT, expires_at=None, updated_at=timezone.now())


@_public_errors
def refresh_connection(user, connection_id, transport=None):
    _enabled()
    _outside_transaction()
    connection = _connection(user, connection_id)
    try:
        vault = _vault()
        with vault.lock(connection.pk):
            connection = _connection(user, connection_id)
            if connection.status in (ProviderConnection.Status.DISCONNECTED, ProviderConnection.Status.RECONNECT):
                raise ConnectionError('reconnect_required')
            credentials = vault.read(connection.pk)
            try:
                vault_expiry = _validate_credentials(credentials, vault, expected=connection)
            except ConnectionError:
                _mark_reconnect(connection, vault, credentials)
                raise
            # A request queued behind another refresh sees its rotated token and
            # fresh expiry and does not exchange the old refresh token again.
            if vault_expiry and vault_expiry > timezone.now() + timedelta(seconds=60):
                metadata = _metadata(credentials, vault_expiry)
                if any(getattr(connection, key) != value for key, value in metadata.items()):
                    ProviderConnection.objects.filter(pk=connection.pk, user=user).update(
                        **metadata, updated_at=timezone.now())
                    connection.refresh_from_db()
                return connection
            try:
                refreshed = oauth.refresh_credentials(credentials, transport=transport)
                expiry = _validate_credentials(refreshed, vault, expected=connection)
            except oauth.OAuthError as exc:
                code = _provider_code(exc)
                if code == 'invalid_grant':
                    _mark_reconnect(connection, vault, credentials)
                raise ConnectionError(code) from None
            except ConnectionError:
                _mark_reconnect(connection, vault, credentials)
                raise
            vault.write(connection.pk, refreshed)
            ProviderConnection.objects.filter(pk=connection.pk, user=user).update(
                **_metadata(refreshed, expiry), updated_at=timezone.now())
            connection.refresh_from_db()
            return connection
    except VaultError:
        raise ConnectionError('vault_unavailable') from None


@dataclass(frozen=True)
class AuthorizedAccessToken:
    value: str = field(repr=False)

    def __str__(self):
        return '<redacted access token>'


@_public_errors
def get_authorized_access_token(user, connection_id):
    """Return only a token after fresh ownership/grant checks, outside DB locks."""
    _enabled()
    _outside_transaction()
    if getattr(settings, 'ASSISTANT_OPENAI_INFERENCE_ENABLED', False) is not True:
        raise ConnectionError('disabled')
    connection = _connection(user, connection_id)
    if not connection.is_active or connection.status != ProviderConnection.Status.READY:
        raise ConnectionError('reconnect_required')
    vault = _vault()
    for refreshed in (False, True):
        with vault.lock(connection.pk):
            connection = _connection(user, connection_id)
            credentials = vault.read(connection.pk)
            expiry = _validate_credentials(credentials, vault, expected=connection)
            if (not connection.is_active or connection.status != ProviderConnection.Status.READY
                    or credentials.get('capability') != 'plan_authorized'
                    or not {'resource.invoke', 'chatgpt.tokens.use.direct'} <= set(credentials['scopes'])
                    or not expiry):
                raise ConnectionError('reconnect_required')
            value = credentials.get('access_token')
            if (not isinstance(value, str) or not value or len(value) > 16384
                    or any(ord(char) < 33 or ord(char) > 126 for char in value)):
                raise ConnectionError('credentials_invalid')
            if expiry > timezone.now() + timedelta(seconds=60) or refreshed:
                if expiry <= timezone.now():
                    raise ConnectionError('reconnect_required')
                return AuthorizedAccessToken(value)
        # Release the record lock before entering the existing refresh owner;
        # it serializes rotations and re-reads the newest token under its lock.
        refresh_connection(user, connection_id)


@_public_errors
def activate_connection(user, connection_id):
    _outside_transaction()
    connection = _connection(user, connection_id)
    if connection.status == ProviderConnection.Status.DISCONNECTED:
        raise ConnectionError('reconnect_required')
    try:
        vault = _vault()
        with vault.lock(_user_lock(user)):
            connection = _connection(user, connection_id)
            if connection.status == ProviderConnection.Status.DISCONNECTED:
                raise ConnectionError('reconnect_required')
            with transaction.atomic():
                ProviderConnection.objects.filter(user=user, is_active=True).update(is_active=False)
                ProviderConnection.objects.filter(pk=connection.pk, user=user).update(is_active=True, updated_at=timezone.now())
            connection.refresh_from_db()
        return connection
    except VaultError:
        raise ConnectionError('vault_unavailable') from None


@_public_errors
def disconnect_connection(user, connection_id, transport=None):
    _outside_transaction()
    connection = _connection(user, connection_id)
    try:
        vault = _vault()
        with vault.lock(_user_lock(user)):
            with vault.lock(connection.pk):
                try:
                    credentials = vault.read(connection.pk)
                except VaultError as exc:
                    if exc.code != 'record_not_found':
                        raise
                    credentials = {}
                revoked = False
                # Local disconnect is always allowed. A disabled installation
                # must not send even a revocation request to the provider.
                identity_matches = (_identity(credentials) == (connection.issuer, connection.subject, connection.client_id)
                                    and credentials.get('host_id') == vault.host_id())
                if (getattr(settings, 'ASSISTANT_OPENAI_AUTH_ENABLED', False) is True and identity_matches
                        and (credentials.get('refresh_token') or credentials.get('access_token'))):
                    try:
                        revoked = bool(oauth.revoke_credentials(credentials, transport=transport))
                    except oauth.OAuthError:
                        pass
                vault.write(connection.pk, _registration(credentials, connection, vault))
                ProviderConnection.objects.filter(pk=connection.pk, user=user).update(
                    status=ProviderConnection.Status.DISCONNECTED, is_active=False,
                    expires_at=None, updated_at=timezone.now())
            for completed in AuthorizationAttempt.objects.filter(
                    user=user, connection=connection, status=AuthorizationAttempt.Status.COMPLETE):
                with vault.lock(completed.vault_id):
                    vault.delete(completed.vault_id)
            connection.refresh_from_db()
            return connection, revoked
    except VaultError:
        raise ConnectionError('vault_unavailable') from None
