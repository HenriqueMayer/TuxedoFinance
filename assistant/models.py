# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Local assistant records; never financial records or credential storage."""
import uuid

from django.conf import settings
from django.db import models


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='assistant_conversations')
    title = models.CharField(max_length=120, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at', '-pk']


class Message(models.Model):
    class Role(models.TextChoices):
        USER = 'user', 'User'
        ASSISTANT = 'assistant', 'Assistant'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=12, choices=Role.choices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']


class ProviderConnection(models.Model):
    """User-owned account metadata; credentials live only in the private vault."""

    class Status(models.TextChoices):
        READY = 'ready', 'Account authorized'
        IDENTITY_ONLY = 'identity_only', 'Identity only'
        RECONNECT = 'reconnect', 'Reconnect required'
        DISCONNECTED = 'disconnected', 'Disconnected'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='assistant_connections')
    provider = models.CharField(max_length=20, default='openai', editable=False)
    issuer = models.CharField(max_length=255)
    subject = models.CharField(max_length=255)
    client_id = models.CharField(max_length=255)
    email = models.EmailField(blank=True, default='')
    scopes = models.JSONField(default=list)
    expires_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IDENTITY_ONLY)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_active', '-updated_at', 'pk']
        constraints = [
            models.UniqueConstraint(fields=['user', 'client_id', 'issuer', 'subject'],
                                    name='assistant_unique_user_identity'),
            models.UniqueConstraint(fields=['user'], condition=models.Q(is_active=True),
                                    name='assistant_single_active_connection'),
        ]


class AuthorizationAttempt(models.Model):
    """One-time session-bound OAuth handoff; PKCE and state stay encrypted."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        EXCHANGING = 'exchanging', 'Exchanging'
        VERIFIED = 'verified', 'Awaiting confirmation'
        FINISHING = 'finishing', 'Finishing'
        COMPLETE = 'complete', 'Complete'
        FAILED = 'failed', 'Failed'
        EXPIRED = 'expired', 'Expired'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='assistant_authorization_attempts')
    session_digest = models.CharField(max_length=64)
    state_digest = models.CharField(max_length=64, unique=True)
    vault_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    connection = models.ForeignKey(ProviderConnection, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='authorization_attempts')
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    error_code = models.CharField(max_length=40, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', 'pk']
        indexes = [models.Index(fields=['user', 'expires_at'], name='assistant_attempt_owner_expiry')]
