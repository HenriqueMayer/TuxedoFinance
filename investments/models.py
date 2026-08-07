"""Investment institutions, products, assets, and manual operations."""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from core.currencies import CURRENCIES


class Institution(models.Model):
    """A bank, broker, exchange, or other investment institution."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='investment_institutions',
    )
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'name'],
                name='unique_investment_institution_per_user',
            ),
        ]

    def __str__(self):
        return self.name


class InvestmentProduct(models.Model):
    """A named product or wallet held at an institution."""

    class YieldMode(models.TextChoices):
        MANUAL = 'MANUAL', 'Manual'
        MONTHLY = 'MONTHLY', 'Monthly rate (Coming soon)'
        ANNUAL = 'ANNUAL', 'Annual rate (Coming soon)'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='investment_products',
    )
    institution = models.ForeignKey(
        Institution,
        on_delete=models.CASCADE,
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
        ordering = ['institution__name', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['institution', 'name'],
                name='unique_investment_product_per_institution',
            ),
        ]

    def __str__(self):
        return f'{self.institution.name} — {self.name}'


class Asset(models.Model):
    """A user-defined asset held inside an investment product."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='investment_assets',
    )
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)
    currency = models.CharField(max_length=3, default=settings.CURRENCY)
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


class Investment(models.Model):
    """One manual deposit, withdrawal, or yield operation."""

    class Kind(models.TextChoices):
        DEPOSIT = 'DEPOSIT', 'Deposit'
        WITHDRAWAL = 'WITHDRAWAL', 'Withdrawal'
        YIELD = 'YIELD', 'Yield'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='investments',
    )
    product = models.ForeignKey(
        InvestmentProduct,
        on_delete=models.PROTECT,
        related_name='operations',
        null=True,
    )
    asset = models.ForeignKey(
        Asset,
        on_delete=models.PROTECT,
        related_name='operations',
        null=True,
    )
    title = models.CharField(max_length=150)
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    date = models.DateField()
    reason = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        asset_code = self.asset.code if self.asset_id else 'legacy'
        return f'{self.title} ({self.get_kind_display()}, {asset_code})'

    @property
    def currency(self):
        """Expose the asset currency for existing aggregation code."""
        return self.asset.currency if self.asset_id else settings.CURRENCY

    @property
    def signed_amount(self):
        """Return the operation's contribution to the asset balance."""
        if self.kind == self.Kind.WITHDRAWAL:
            return -self.amount
        return self.amount


class ExchangeRate(models.Model):
    """A manual exchange rate used for supported fiat currencies."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='exchange_rates',
    )
    from_currency = models.CharField(
        max_length=3,
        choices=[(code, currency.name) for code, currency in CURRENCIES.items()],
    )
    to_currency = models.CharField(
        max_length=3,
        choices=[(code, currency.name) for code, currency in CURRENCIES.items()],
    )
    rate = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        validators=[MinValueValidator(Decimal('0.00000001'))],
    )
    effective_date = models.DateField()
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-effective_date', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'from_currency', 'to_currency', 'effective_date'],
                name='unique_rate_per_pair_date_per_user',
            ),
        ]

    def __str__(self):
        return (
            f'1 {self.from_currency} = {self.rate} {self.to_currency} '
            f'(as of {self.effective_date})'
        )
