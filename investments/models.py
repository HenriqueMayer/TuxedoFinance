"""Investment products, assets, and portfolio operations."""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.currencies import CURRENCIES


POSITIVE_8DP = MinValueValidator(Decimal('0.00000001'))
POSITIVE_CENTS = MinValueValidator(Decimal('0.01'))
NON_NEGATIVE = MinValueValidator(Decimal('0.00'))
ZERO = Decimal('0.00')
CURRENCY_NAMES = {
    'BRL': _('Brazilian Real'),
    'USD': _('US Dollar'),
    'EUR': _('Euro'),
    'GBP': _('British Pound'),
    'JPY': _('Japanese Yen'),
    'CHF': _('Swiss Franc'),
}
CURRENCY_CHOICES = [
    (code, CURRENCY_NAMES.get(code, currency.name))
    for code, currency in CURRENCIES.items()
]


class InvestmentProduct(models.Model):
    class YieldMode(models.TextChoices):
        MANUAL = 'MANUAL', _('Manual')
        MONTHLY = 'MONTHLY', _('Monthly rate (Coming soon)')
        ANNUAL = 'ANNUAL', _('Annual rate (Coming soon)')

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='investment_products',
    )
    bank = models.ForeignKey(
        'banking.Bank',
        on_delete=models.PROTECT,
        related_name='investment_products',
    )
    name = models.CharField(max_length=150)
    yield_mode = models.CharField(
        max_length=20,
        choices=YieldMode.choices,
        default=YieldMode.MANUAL,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['bank__name', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['bank', 'name'],
                name='investments_unique_product_bank_name',
            ),
        ]

    def __str__(self):
        return f'{self.bank.name} - {self.name}'

    def clean(self):
        if self.bank_id and self.user_id and self.bank.user_id != self.user_id:
            raise ValidationError({'bank': _('The bank must belong to the product owner.')})


class Asset(models.Model):
    class ValuationMode(models.TextChoices):
        MONETARY = 'MONETARY', _('Monetary value')
        UNITS = 'UNITS', _('Units and price')

    class AssetClass(models.TextChoices):
        LIQUIDITY = 'LIQUIDITY', _('Liquidity')
        CURRENCY = 'CURRENCY', _('Currency')
        CRYPTO = 'CRYPTO', _('Crypto')
        FIXED_INCOME = 'FIXED_INCOME', _('Fixed income')
        EQUITY = 'EQUITY', _('Equity')
        OTHER = 'OTHER', _('Other')

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='investment_assets',
    )
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)
    asset_class = models.CharField(max_length=20, choices=AssetClass.choices)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES)
    valuation_mode = models.CharField(
        max_length=10, choices=ValuationMode.choices, default=ValuationMode.UNITS
    )
    opening_balance = models.DecimalField(
        max_digits=16, decimal_places=2, default=ZERO, validators=[NON_NEGATIVE],
        help_text=_('Existing balance before the first recorded operation.'),
    )
    opening_product = models.ForeignKey(
        InvestmentProduct, on_delete=models.PROTECT, related_name='opening_balance_assets',
        null=True, blank=True, help_text=_('Product that holds the opening balance.'),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'code'],
                name='unique_investment_asset_code_per_user',
            ),
        ]

    def __str__(self):
        return f'{self.name} ({self.code})'

    def clean(self):
        errors = {}
        if self.valuation_mode == self.ValuationMode.UNITS:
            if self.opening_balance != ZERO:
                errors['opening_balance'] = _('Only monetary assets can have an opening balance.')
            if self.opening_product_id:
                errors['opening_product'] = _('Only monetary assets can have an opening balance.')
        elif self.opening_balance > ZERO and not self.opening_product_id:
            errors['opening_product'] = _('Select the product that holds the opening balance.')
        elif self.opening_balance == ZERO and self.opening_product_id:
            errors['opening_product'] = _('Select an opening product only when there is an opening balance.')
        if self.opening_product_id and self.user_id and self.opening_product.user_id != self.user_id:
            errors['opening_product'] = _('The opening product must belong to the asset owner.')
        if errors:
            raise ValidationError(errors)


class Investment(models.Model):
    """A quantity-changing portfolio operation and its optional cash side."""

    class Kind(models.TextChoices):
        DEPOSIT = 'DEPOSIT', _('Deposit')
        WITHDRAWAL = 'WITHDRAWAL', _('Withdrawal')
        YIELD = 'YIELD', _('Yield')

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='investments',
    )
    product = models.ForeignKey(
        InvestmentProduct,
        on_delete=models.PROTECT,
        related_name='operations',
    )
    asset = models.ForeignKey(
        Asset,
        on_delete=models.PROTECT,
        related_name='operations',
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    quantity = models.DecimalField(
        max_digits=20, decimal_places=8, validators=[POSITIVE_8DP], null=True, blank=True
    )
    unit_price = models.DecimalField(
        max_digits=20, decimal_places=8, validators=[POSITIVE_8DP], null=True, blank=True
    )
    amount = models.DecimalField(
        max_digits=16, decimal_places=2, validators=[POSITIVE_CENTS], null=True, blank=True,
        help_text=_('Position value for monetary assets.'),
    )
    fees = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[NON_NEGATIVE],
    )
    cash_amount = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[POSITIVE_CENTS],
        help_text=_('Native amount debited from or credited to the selected account.'),
    )
    source_account = models.ForeignKey(
        'banking.BankAccount',
        on_delete=models.PROTECT,
        related_name='funded_investments',
        null=True,
        blank=True,
    )
    source_program = models.ForeignKey(
        'banking.LoyaltyProgram',
        on_delete=models.PROTECT,
        related_name='funded_investments',
        null=True,
        blank=True,
    )
    source_points = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[POSITIVE_CENTS],
    )
    destination_account = models.ForeignKey(
        'banking.BankAccount',
        on_delete=models.PROTECT,
        related_name='investment_withdrawals',
        null=True,
        blank=True,
    )
    bank_movement = models.OneToOneField(
        'banking.BankMovement',
        on_delete=models.SET_NULL,
        related_name='investment_operation',
        null=True,
        blank=True,
        editable=False,
    )
    loyalty_entry = models.OneToOneField(
        'banking.LoyaltyEntry',
        on_delete=models.SET_NULL,
        related_name='investment_operation',
        null=True,
        blank=True,
        editable=False,
    )
    date = models.DateField()
    reason = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__isnull=True) | models.Q(quantity__gt=0),
                name='investments_quantity_null_or_gt_zero',
            ),
            models.CheckConstraint(
                condition=models.Q(unit_price__isnull=True) | models.Q(unit_price__gt=0),
                name='investments_unit_price_null_or_gt_zero',
            ),
            models.CheckConstraint(
                condition=models.Q(fees__gte=0),
                name='investments_fees_gte_zero',
            ),
            models.CheckConstraint(
                condition=models.Q(cash_amount__isnull=True) | models.Q(cash_amount__gt=0),
                name='investments_cash_amount_null_or_gt_zero',
            ),
            models.CheckConstraint(
                condition=models.Q(source_points__isnull=True) | models.Q(source_points__gt=0),
                name='investments_source_points_null_or_gt_zero',
            ),
            models.CheckConstraint(
                condition=models.Q(amount__isnull=True) | models.Q(amount__gt=0),
                name='investments_amount_null_or_gt_zero',
            ),
        ]

    def __str__(self):
        return f'{self.get_kind_display()} {self.asset.code}'

    @property
    def currency(self):
        return self.asset.currency

    @property
    def gross_value(self):
        if self.asset.valuation_mode == Asset.ValuationMode.MONETARY:
            return self.amount
        return self.quantity * self.unit_price

    @property
    def signed_quantity(self):
        if self.asset.valuation_mode == Asset.ValuationMode.MONETARY:
            return ZERO
        return -self.quantity if self.kind == self.Kind.WITHDRAWAL else self.quantity

    @property
    def signed_value(self):
        return -self.gross_value if self.kind == self.Kind.WITHDRAWAL else self.gross_value

    def clean(self):
        errors = {}
        owned = {
            'product': self.product if self.product_id else None,
            'asset': self.asset if self.asset_id else None,
            'source_account': self.source_account if self.source_account_id else None,
            'source_program': self.source_program if self.source_program_id else None,
            'destination_account': (
                self.destination_account if self.destination_account_id else None
            ),
        }
        for field, obj in owned.items():
            if obj and self.user_id and obj.user_id != self.user_id:
                errors[field] = _('This selection must belong to the operation owner.')
        if self.product_id and self.user_id and self.product.bank.user_id != self.user_id:
            errors['product'] = _('The product bank must belong to the operation owner.')

        if self.asset_id and self.asset.valuation_mode == Asset.ValuationMode.MONETARY:
            if self.amount is None or self.amount <= 0:
                errors['amount'] = _('Monetary assets require a positive investment amount.')
            if self.quantity is not None:
                errors['quantity'] = _('Monetary assets do not use quantity.')
            if self.unit_price is not None:
                errors['unit_price'] = _('Monetary assets do not use a unit price.')
        elif self.asset_id:
            if self.quantity is None or self.quantity <= 0:
                errors['quantity'] = _('Unit-based assets require a positive quantity.')
            if self.unit_price is None or self.unit_price <= 0:
                errors['unit_price'] = _('Unit-based assets require a positive unit price.')
            if self.amount is not None:
                errors['amount'] = _('Unit-based assets derive value from quantity and unit price.')

        has_account = self.source_account_id is not None
        has_program = self.source_program_id is not None
        has_destination = self.destination_account_id is not None
        has_cash = self.cash_amount is not None
        has_points = self.source_points is not None

        if self.kind == self.Kind.DEPOSIT:
            if has_account == has_program:
                errors['source_account'] = _('Deposit requires exactly one funding source.')
                errors['source_program'] = _('Deposit requires exactly one funding source.')
            if has_destination:
                errors['destination_account'] = _('Deposit does not use a destination account.')
            if has_account:
                if not has_cash or self.cash_amount <= 0:
                    errors['cash_amount'] = _('Account-funded deposit requires a positive cash amount.')
                if has_points:
                    errors['source_points'] = _('Account-funded deposit does not use points.')
            if has_program and (not has_points or self.source_points <= 0):
                errors['source_points'] = _('Program-funded deposit requires positive points.')
        elif self.kind == self.Kind.WITHDRAWAL:
            if not has_destination:
                errors['destination_account'] = _('Withdrawal requires a destination account.')
            if not has_cash or self.cash_amount <= 0:
                errors['cash_amount'] = _('Withdrawal requires a positive cash amount.')
            if has_account:
                errors['source_account'] = _('Withdrawal does not use a funding account.')
            if has_program:
                errors['source_program'] = _('Withdrawal does not use a loyalty program.')
            if has_points:
                errors['source_points'] = _('Withdrawal does not use points.')
        elif self.kind == self.Kind.YIELD:
            for field, present in (
                ('source_account', has_account),
                ('source_program', has_program),
                ('source_points', has_points),
                ('destination_account', has_destination),
                ('cash_amount', has_cash),
            ):
                if present:
                    errors[field] = _('Yield is internal and does not use cash or funding fields.')

        if errors:
            raise ValidationError(errors)
