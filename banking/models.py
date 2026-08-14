from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Case, DecimalField, F, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils.translation import gettext as gettext
from django.utils.translation import gettext_lazy as _

from core.currencies import CURRENCIES


CURRENCY_NAMES = {
    'BRL': _('Brazilian Real'),
    'USD': _('US Dollar'),
    'EUR': _('Euro'),
    'GBP': _('British Pound'),
    'JPY': _('Japanese Yen'),
    'CHF': _('Swiss Franc'),
}
CURRENCY_CHOICES = [(code, CURRENCY_NAMES[code]) for code in CURRENCIES]
ZERO = Decimal('0.00')
POSITIVE = MinValueValidator(Decimal('0.01'))
NON_NEGATIVE = MinValueValidator(ZERO)


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Bank(TimestampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='banks'
    )
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'name'], name='banking_unique_bank_user_name'
            )
        ]

    def __str__(self):
        return self.name


class BankAccount(TimestampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bank_accounts',
    )
    bank = models.ForeignKey(Bank, on_delete=models.PROTECT, related_name='accounts')
    name = models.CharField(max_length=100)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES)
    opening_balance = models.DecimalField(
        max_digits=16, decimal_places=2, default=ZERO
    )
    pix_enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ['bank__name', 'name', 'currency']
        constraints = [
            models.UniqueConstraint(
                fields=['bank', 'name', 'currency'],
                name='banking_unique_account_bank_name_currency',
            )
        ]

    def __str__(self):
        return f'{self.bank.name} - {self.name} ({self.currency})'

    def clean(self):
        if self.bank_id and self.user_id and self.bank.user_id != self.user_id:
            raise ValidationError({'bank': _('The bank must belong to the account owner.')})

    def current_balance(self, as_of=None):
        from banking.services import account_balance

        return account_balance(self, as_of=as_of)


class DebitCard(TimestampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='debit_cards'
    )
    account = models.ForeignKey(
        BankAccount, on_delete=models.PROTECT, related_name='debit_cards'
    )
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['account', 'name'], name='banking_unique_debit_card_account_name'
            )
        ]

    def __str__(self):
        return self.name

    def clean(self):
        if self.account_id and self.user_id and self.account.user_id != self.user_id:
            raise ValidationError({'account': _('The account must belong to the card owner.')})


class CreditCard(TimestampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='credit_cards'
    )
    account = models.ForeignKey(
        BankAccount, on_delete=models.PROTECT, related_name='credit_cards'
    )
    name = models.CharField(max_length=100)
    closing_day = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(31)]
    )
    due_day = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(31)]
    )

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['account', 'name'], name='banking_unique_credit_card_account_name'
            )
        ]

    def __str__(self):
        return self.name

    def clean(self):
        if self.account_id and self.user_id and self.account.user_id != self.user_id:
            raise ValidationError({'account': _('The account must belong to the card owner.')})

    def statement_month(self, purchase_date, override=None):
        if override not in (None, 0, 1):
            raise ValueError('override must be None, 0, or 1.')
        if override is None:
            closing_day = min(
                self.closing_day, monthrange(purchase_date.year, purchase_date.month)[1]
            )
            offset = 1 if purchase_date.day >= closing_day else 0
        else:
            offset = override
        index = purchase_date.year * 12 + purchase_date.month - 1 + offset
        year, month = divmod(index, 12)
        return date(year, month + 1, 1)

    def due_date_for(self, reference_month):
        reference_month = reference_month.replace(day=1)
        day = min(self.due_day, monthrange(reference_month.year, reference_month.month)[1])
        return reference_month.replace(day=day)


class CardInvoice(TimestampedModel):
    class Status(models.TextChoices):
        SCHEDULED = 'SCHEDULED', _('Scheduled')
        PAID = 'PAID', _('Paid')

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='card_invoices'
    )
    card = models.ForeignKey(
        CreditCard, on_delete=models.PROTECT, related_name='invoices'
    )
    reference_month = models.DateField()
    due_date = models.DateField()
    amount = models.DecimalField(
        max_digits=16, decimal_places=2, validators=[NON_NEGATIVE]
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.SCHEDULED
    )
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-reference_month', 'card__name']
        constraints = [
            models.UniqueConstraint(
                fields=['card', 'reference_month'],
                name='banking_unique_invoice_card_month',
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gte=0), name='banking_invoice_amount_gte_zero'
            ),
        ]

    def __str__(self):
        return f'{self.card.name} - {self.reference_month:%Y-%m}'

    @property
    def account(self):
        return self.card.account

    @property
    def is_overdue(self):
        return self.status == self.Status.SCHEDULED and self.due_date < date.today()

    def clean(self):
        errors = {}
        if self.card_id and self.user_id and self.card.user_id != self.user_id:
            errors['card'] = _('The card must belong to the invoice owner.')
        if self.reference_month and self.reference_month.day != 1:
            errors['reference_month'] = _('Reference month must be the first day of a month.')
        if errors:
            raise ValidationError(errors)


class BankTransfer(TimestampedModel):
    class FxSnapshotStatus(models.TextChoices):
        UNKNOWN = 'UNKNOWN', _('Unknown')
        RECONSTRUCTED = 'RECONSTRUCTED', _('Reconstructed')
        CAPTURED = 'CAPTURED', _('Captured')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bank_transfers'
    )
    source_account = models.ForeignKey(
        BankAccount, on_delete=models.PROTECT, related_name='outgoing_transfers'
    )
    destination_account = models.ForeignKey(
        BankAccount, on_delete=models.PROTECT, related_name='incoming_transfers'
    )
    source_amount = models.DecimalField(
        max_digits=16, decimal_places=2, validators=[POSITIVE]
    )
    destination_amount = models.DecimalField(
        max_digits=16, decimal_places=2, validators=[POSITIVE]
    )
    fx_rate = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    fx_source_currency = models.CharField(max_length=3, blank=True)
    fx_target_currency = models.CharField(max_length=3, blank=True)
    fx_effective_date = models.DateField(null=True, blank=True)
    fx_source_rate = models.ForeignKey(
        'ExchangeRate', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='transfer_snapshots',
    )
    fx_snapshot_status = models.CharField(
        max_length=15, choices=FxSnapshotStatus.choices, default=FxSnapshotStatus.UNKNOWN
    )
    date = models.DateField()
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-date', '-created_at']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(source_amount__gt=0),
                name='banking_transfer_source_amount_gt_zero',
            ),
            models.CheckConstraint(
                condition=models.Q(destination_amount__gt=0),
                name='banking_transfer_destination_amount_gt_zero',
            ),
            models.CheckConstraint(
                condition=~models.Q(source_account=F('destination_account')),
                name='banking_transfer_accounts_differ',
            ),
        ]

    def __str__(self):
        return gettext('%(source)s to %(destination)s') % {
            'source': self.source_account,
            'destination': self.destination_account,
        }

    def clean(self):
        errors = {}
        if self.source_account_id and self.destination_account_id:
            if self.source_account_id == self.destination_account_id:
                errors['destination_account'] = _('Source and destination must differ.')
            if self.source_account.user_id != self.destination_account.user_id:
                errors['destination_account'] = _('Both accounts must have the same owner.')
        for field in ('source_account', 'destination_account'):
            account = getattr(self, field, None)
            if account and self.user_id and account.user_id != self.user_id:
                errors[field] = _('The account must belong to the transfer owner.')
        if errors:
            raise ValidationError(errors)


class BankMovement(TimestampedModel):
    class Direction(models.TextChoices):
        CREDIT = 'CREDIT', _('Credit')
        DEBIT = 'DEBIT', _('Debit')

    class Kind(models.TextChoices):
        INCOME = 'INCOME', _('Income')
        EXPENSE = 'EXPENSE', _('Expense')
        TRANSFER = 'TRANSFER', _('Transfer')
        INVOICE = 'INVOICE', _('Invoice')
        INVESTMENT = 'INVESTMENT', _('Investment')
        REWARD = 'REWARD', _('Reward')
        ADJUSTMENT = 'ADJUSTMENT', _('Adjustment')

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bank_movements'
    )
    account = models.ForeignKey(
        BankAccount, on_delete=models.PROTECT, related_name='movements'
    )
    direction = models.CharField(max_length=6, choices=Direction.choices)
    kind = models.CharField(max_length=12, choices=Kind.choices)
    amount = models.DecimalField(max_digits=16, decimal_places=2, validators=[POSITIVE])
    effective_date = models.DateField()
    description = models.CharField(max_length=255, blank=True)
    invoice = models.OneToOneField(
        CardInvoice,
        on_delete=models.PROTECT,
        related_name='settlement_movement',
        null=True,
        blank=True,
    )
    transfer = models.ForeignKey(
        BankTransfer,
        on_delete=models.PROTECT,
        related_name='movements',
        null=True,
        blank=True,
    )
    source_key = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ['-effective_date', '-created_at']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name='banking_movement_amount_gt_zero'
            ),
            models.UniqueConstraint(
                fields=['user', 'source_key'],
                condition=~models.Q(source_key=''),
                name='banking_unique_movement_source_key',
            ),
        ]

    def __str__(self):
        return f'{self.get_direction_display()} {self.amount} {self.account.currency}'

    @property
    def signed_amount(self):
        return self.amount if self.direction == self.Direction.CREDIT else -self.amount

    def clean(self):
        errors = {}
        if self.account_id and self.user_id and self.account.user_id != self.user_id:
            errors['account'] = _('The account must belong to the movement owner.')
        if self.invoice_id:
            if self.user_id and self.invoice.user_id != self.user_id:
                errors['invoice'] = _('The invoice must belong to the movement owner.')
            elif self.account_id and self.invoice.account_id != self.account_id:
                errors['invoice'] = _('The invoice must settle from its linked account.')
            if self.kind != self.Kind.INVOICE or self.direction != self.Direction.DEBIT:
                errors['invoice'] = _('Invoice settlements must be INVOICE debit movements.')
        if self.transfer_id:
            if self.user_id and self.transfer.user_id != self.user_id:
                errors['transfer'] = _('The transfer must belong to the movement owner.')
            if self.kind != self.Kind.TRANSFER:
                errors['kind'] = _('A transfer-linked movement must have TRANSFER kind.')
        if errors:
            raise ValidationError(errors)


class LoyaltyProgram(TimestampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='loyalty_programs',
    )
    name = models.CharField(max_length=100)
    bank = models.ForeignKey(
        Bank,
        on_delete=models.SET_NULL,
        related_name='loyalty_programs',
        null=True,
        blank=True,
    )
    cards = models.ManyToManyField(CreditCard, related_name='loyalty_programs', blank=True)
    unit_name = models.CharField(max_length=30, default='Points')

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'name'], name='banking_unique_loyalty_user_name'
            )
        ]

    def __str__(self):
        return self.name

    def clean(self):
        if self.bank_id and self.user_id and self.bank.user_id != self.user_id:
            raise ValidationError({'bank': _('The bank must belong to the program owner.')})

    def validate_cards(self, cards):
        if any(card.user_id != self.user_id for card in cards):
            raise ValidationError({'cards': _('Every card must belong to the program owner.')})

    @property
    def balance(self):
        amount_field = DecimalField(max_digits=16, decimal_places=2)
        return self.entries.aggregate(
            total=Coalesce(
                Sum(
                    Case(
                        When(direction=LoyaltyEntry.Direction.CREDIT, then=F('amount')),
                        default=-F('amount'),
                        output_field=amount_field,
                    )
                ),
                Value(ZERO),
                output_field=amount_field,
            )
        )['total']


class LoyaltyEntry(models.Model):
    class Direction(models.TextChoices):
        CREDIT = 'CREDIT', _('Credit')
        DEBIT = 'DEBIT', _('Debit')

    class Kind(models.TextChoices):
        INVOICE_AWARD = 'INVOICE_AWARD', _('Invoice award')
        PURCHASE = 'PURCHASE', _('Purchase')
        ADJUSTMENT = 'ADJUSTMENT', _('Adjustment')
        EXPIRATION = 'EXPIRATION', _('Expiration')
        REDEMPTION = 'REDEMPTION', _('Redemption')

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='loyalty_entries'
    )
    program = models.ForeignKey(
        LoyaltyProgram, on_delete=models.PROTECT, related_name='entries'
    )
    direction = models.CharField(max_length=6, choices=Direction.choices)
    kind = models.CharField(max_length=13, choices=Kind.choices)
    amount = models.DecimalField(max_digits=16, decimal_places=2, validators=[POSITIVE])
    date = models.DateField()
    invoice = models.ForeignKey(
        CardInvoice,
        on_delete=models.SET_NULL,
        related_name='loyalty_entries',
        null=True,
        blank=True,
    )
    funding_account = models.ForeignKey(
        BankAccount,
        on_delete=models.PROTECT,
        related_name='funded_loyalty_entries',
        null=True,
        blank=True,
    )
    funding_credit_card = models.ForeignKey(
        CreditCard,
        on_delete=models.PROTECT,
        related_name='funded_loyalty_entries',
        null=True,
        blank=True,
    )
    cash_amount = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        validators=[POSITIVE],
        null=True,
        blank=True,
    )
    funding_movement = models.OneToOneField(
        BankMovement,
        on_delete=models.SET_NULL,
        related_name='loyalty_purchase',
        null=True,
        blank=True,
        editable=False,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-date', '-pk']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name='banking_loyalty_amount_gt_zero'
            )
        ]

    def __str__(self):
        return f'{self.program.name}: {self.direction} {self.amount}'

    def clean(self):
        errors = {}
        if self.program_id and self.user_id and self.program.user_id != self.user_id:
            errors['program'] = _('The program must belong to the entry owner.')
        if self.invoice_id and self.user_id and self.invoice.user_id != self.user_id:
            errors['invoice'] = _('The invoice must belong to the entry owner.')
        if self.invoice_id and self.kind != self.Kind.INVOICE_AWARD:
            errors['invoice'] = _('Only invoice awards may reference an invoice.')
        if self.invoice_id and self.program_id:
            linked_card_ids = set(self.program.cards.values_list('pk', flat=True))
            if linked_card_ids and self.invoice.card_id not in linked_card_ids:
                errors['invoice'] = _('The invoice card is not linked to this program.')

        funding_count = int(self.funding_account_id is not None) + int(
            self.funding_credit_card_id is not None
        )
        if self.kind == self.Kind.PURCHASE:
            if self.direction != self.Direction.CREDIT:
                errors['direction'] = _('Purchased points must be a credit.')
            if funding_count != 1:
                errors['funding_account'] = _('A purchase requires exactly one funding instrument.')
            if self.cash_amount is None or self.cash_amount <= ZERO:
                errors['cash_amount'] = _('A purchase requires a positive cash amount.')
        elif funding_count or self.cash_amount is not None:
            errors['funding_account'] = _('Funding fields are only used when purchasing points.')

        if self.kind == self.Kind.INVOICE_AWARD and self.direction != self.Direction.CREDIT:
            errors['direction'] = _('Invoice points must be a credit.')
        if self.kind in {self.Kind.EXPIRATION, self.Kind.REDEMPTION} and self.direction != self.Direction.DEBIT:
            errors['direction'] = _('Expiration and redemption entries must be debits.')

        for field in ('funding_account', 'funding_credit_card'):
            instrument = getattr(self, field, None)
            if instrument and self.user_id and instrument.user_id != self.user_id:
                errors[field] = _('The funding instrument must belong to the entry owner.')
        if errors:
            raise ValidationError(errors)


class RewardRedemption(TimestampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reward_redemptions',
    )
    program = models.ForeignKey(
        LoyaltyProgram, on_delete=models.PROTECT, related_name='redemptions'
    )
    points = models.DecimalField(max_digits=16, decimal_places=2, validators=[POSITIVE])
    target_account = models.ForeignKey(
        BankAccount, on_delete=models.PROTECT, related_name='reward_redemptions'
    )
    target_amount = models.DecimalField(
        max_digits=16, decimal_places=2, validators=[POSITIVE]
    )
    iof_amount = models.DecimalField(
        max_digits=16, decimal_places=2, default=ZERO, validators=[NON_NEGATIVE]
    )
    iof_account = models.ForeignKey(
        BankAccount,
        on_delete=models.PROTECT,
        related_name='iof_reward_redemptions',
        null=True,
        blank=True,
    )
    iof_credit_card = models.ForeignKey(
        CreditCard,
        on_delete=models.PROTECT,
        related_name='iof_reward_redemptions',
        null=True,
        blank=True,
    )
    date = models.DateField()
    notes = models.TextField(blank=True)
    loyalty_entry = models.OneToOneField(
        LoyaltyEntry,
        on_delete=models.PROTECT,
        related_name='reward_redemption',
        null=True,
        blank=True,
        editable=False,
    )
    reward_movement = models.OneToOneField(
        BankMovement,
        on_delete=models.PROTECT,
        related_name='reward_redemption',
        null=True,
        blank=True,
        editable=False,
    )
    iof_movement = models.OneToOneField(
        BankMovement,
        on_delete=models.PROTECT,
        related_name='reward_iof_redemption',
        null=True,
        blank=True,
        editable=False,
    )

    class Meta:
        ordering = ['-date', '-created_at']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(points__gt=0), name='banking_redemption_points_gt_zero'
            ),
            models.CheckConstraint(
                condition=models.Q(target_amount__gt=0),
                name='banking_redemption_target_amount_gt_zero',
            ),
            models.CheckConstraint(
                condition=models.Q(iof_amount__gte=0),
                name='banking_redemption_iof_amount_gte_zero',
            ),
        ]

    def __str__(self):
        return gettext('%(program)s: %(points)s points') % {
            'program': self.program.name,
            'points': self.points,
        }

    @property
    def has_pending_credit_card_iof(self):
        """True until another app posts this IOF charge to the card invoice."""
        return self.iof_amount > ZERO and self.iof_credit_card_id is not None

    def clean(self):
        errors = {}
        owned = {
            'program': self.program if self.program_id else None,
            'target_account': self.target_account if self.target_account_id else None,
            'iof_account': self.iof_account if self.iof_account_id else None,
            'iof_credit_card': self.iof_credit_card if self.iof_credit_card_id else None,
        }
        for field, obj in owned.items():
            if obj and self.user_id and obj.user_id != self.user_id:
                errors[field] = _('This funding instrument must belong to the redemption owner.')
        funding_count = int(self.iof_account_id is not None) + int(
            self.iof_credit_card_id is not None
        )
        if self.iof_amount is not None:
            if self.iof_amount > ZERO and funding_count != 1:
                errors['iof_amount'] = _('Positive IOF requires exactly one funding instrument.')
            elif self.iof_amount == ZERO and funding_count:
                errors['iof_amount'] = _('Do not select an IOF instrument when IOF is zero.')
        if errors:
            raise ValidationError(errors)


class ExchangeRate(TimestampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='banking_exchange_rates',
    )
    from_currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES)
    to_currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES)
    rate = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        validators=[MinValueValidator(Decimal('0.00000001'))],
    )
    effective_date = models.DateField()
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-effective_date', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'from_currency', 'to_currency', 'effective_date'],
                name='banking_unique_exchange_pair_date',
            ),
            models.CheckConstraint(
                condition=models.Q(rate__gt=0), name='banking_exchange_rate_gt_zero'
            ),
            models.CheckConstraint(
                condition=~models.Q(from_currency=F('to_currency')),
                name='banking_exchange_currencies_differ',
            ),
        ]

    def __str__(self):
        return f'1 {self.from_currency} = {self.rate} {self.to_currency}'

    def clean(self):
        if self.from_currency and self.from_currency == self.to_currency:
            raise ValidationError({'to_currency': _('Currencies must differ.')})
