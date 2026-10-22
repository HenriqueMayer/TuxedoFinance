# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Local statement evidence and explicitly reviewed accounting decisions."""
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class ImportBatch(models.Model):
    class Status(models.TextChoices):
        STAGED = 'STAGED', _('Choose columns')
        READY = 'READY', _('Review entries')
        CONFIRMED = 'CONFIRMED', _('Confirmed')
        UNDONE = 'UNDONE', _('Undone')

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    account = models.ForeignKey('banking.BankAccount', on_delete=models.PROTECT)
    file_name = models.CharField(max_length=255)
    file_hash = models.CharField(max_length=64)
    file_format = models.CharField(max_length=3, choices=[('CSV', 'CSV'), ('OFX', 'OFX')])
    encoding = models.CharField(max_length=20, default='utf-8-sig')
    raw_text = models.TextField()
    headers = models.JSONField(default=list)
    mapping = models.JSONField(default=dict)
    metadata = models.JSONField(default=dict)
    closing_balance = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    closing_date = models.DateField(null=True, blank=True)
    reconciliation_at_confirmation = models.JSONField(default=dict)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.STAGED)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    undone_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        constraints = [models.UniqueConstraint(
            fields=['user', 'account', 'file_hash'], condition=~models.Q(status='UNDONE'),
            name='ingestion_unique_active_file',
        )]


class ImportedRow(models.Model):
    class Action(models.TextChoices):
        SKIP = 'SKIP', _('Skip')
        CREATE = 'CREATE', _('Create income or expense')
        MATCH = 'MATCH', _('Match existing cash movement')
        PAY_INVOICE = 'PAY_INVOICE', _('Confirm invoice payment')
        TRANSFER = 'TRANSFER', _('Transfer between my accounts')

    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name='rows')
    number = models.PositiveSmallIntegerField()
    date = models.DateField()
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    description = models.CharField(max_length=1000)
    currency = models.CharField(max_length=3)
    external_id = models.CharField(max_length=255, blank=True)
    raw = models.JSONField(default=dict)
    action = models.CharField(max_length=11, choices=Action.choices, blank=True)
    category = models.ForeignKey('categories.Category', on_delete=models.SET_NULL, null=True, blank=True)
    matched_movement = models.ForeignKey('banking.BankMovement', on_delete=models.SET_NULL, null=True, blank=True, related_name='statement_matches')
    invoice = models.ForeignKey('banking.CardInvoice', on_delete=models.SET_NULL, null=True, blank=True)
    counterparty_account = models.ForeignKey('banking.BankAccount', on_delete=models.SET_NULL, null=True, blank=True)
    counterparty_amount = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    created_transaction = models.ForeignKey('transactions.Transaction', on_delete=models.SET_NULL, null=True, blank=True, related_name='statement_provenance')
    created_payment = models.ForeignKey('banking.InvoicePayment', on_delete=models.SET_NULL, null=True, blank=True, related_name='statement_provenance')
    created_transfer = models.ForeignKey('banking.BankTransfer', on_delete=models.SET_NULL, null=True, blank=True, related_name='statement_provenance')
    created_snapshot = models.JSONField(default=dict)

    class Meta:
        ordering = ['number', 'pk']
        constraints = [models.UniqueConstraint(fields=['batch', 'number'], name='ingestion_unique_row_number')]


class ExternalStatementIdentity(models.Model):
    """Strong bank identifiers only; descriptive hashes are suggestions."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    account = models.ForeignKey('banking.BankAccount', on_delete=models.PROTECT)
    external_id = models.CharField(max_length=255)
    row = models.OneToOneField(ImportedRow, on_delete=models.CASCADE, related_name='identity')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'account', 'external_id'], name='ingestion_unique_bank_identifier')]
