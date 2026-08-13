from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from banking.models import BankAccount, CreditCard, DebitCard
from categories.models import Category


ZERO = Decimal('0.00')


class Transaction(models.Model):
    MAX_INSTALLMENTS = 48

    class TransactionType(models.TextChoices):
        INCOME = 'INCOME', gettext_lazy('Income')
        EXPENSE = 'EXPENSE', gettext_lazy('Expense')

    class PaymentChannel(models.TextChoices):
        ACCOUNT = 'ACCOUNT', gettext_lazy('Bank account')
        PIX = 'PIX', gettext_lazy('PIX')
        DEBIT_CARD = 'DEBIT_CARD', gettext_lazy('Debit card')
        CREDIT_CARD = 'CREDIT_CARD', gettext_lazy('Credit card')

    class BillChoice(models.IntegerChoices):
        CURRENT = 0, gettext_lazy('Current bill')
        NEXT = 1, gettext_lazy('Next bill')

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='transactions'
    )
    title = models.CharField(max_length=150)
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name='transactions'
    )
    payment_channel = models.CharField(max_length=20, choices=PaymentChannel.choices)
    bank_account = models.ForeignKey(
        BankAccount,
        on_delete=models.PROTECT,
        related_name='transactions',
        null=True,
        blank=True,
    )
    debit_card = models.ForeignKey(
        DebitCard,
        on_delete=models.PROTECT,
        related_name='transactions',
        null=True,
        blank=True,
    )
    credit_card = models.ForeignKey(
        CreditCard,
        on_delete=models.PROTECT,
        related_name='transactions',
        null=True,
        blank=True,
    )
    installments = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_INSTALLMENTS)],
    )
    billing_override = models.PositiveSmallIntegerField(
        choices=BillChoice.choices, null=True, blank=True, default=None
    )
    is_fixed = models.BooleanField(default=False)
    fixed_until = models.DateField(null=True, blank=True)
    date = models.DateField()
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name='transactions_amount_gt_zero',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        payment_channel__in=['ACCOUNT', 'PIX'],
                        bank_account__isnull=False,
                        debit_card__isnull=True,
                        credit_card__isnull=True,
                    )
                    | models.Q(
                        payment_channel='DEBIT_CARD',
                        bank_account__isnull=True,
                        debit_card__isnull=False,
                        credit_card__isnull=True,
                    )
                    | models.Q(
                        payment_channel='CREDIT_CARD',
                        bank_account__isnull=True,
                        debit_card__isnull=True,
                        credit_card__isnull=False,
                    )
                ),
                name='transactions_coherent_payment_instrument',
            ),
        ]

    def __str__(self):
        return f'{self.title} ({self.get_transaction_type_display()})'

    def clean(self):
        errors = {}
        instruments = {
            'bank_account': self.bank_account if self.bank_account_id else None,
            'debit_card': self.debit_card if self.debit_card_id else None,
            'credit_card': self.credit_card if self.credit_card_id else None,
        }
        expected = {
            self.PaymentChannel.ACCOUNT: 'bank_account',
            self.PaymentChannel.PIX: 'bank_account',
            self.PaymentChannel.DEBIT_CARD: 'debit_card',
            self.PaymentChannel.CREDIT_CARD: 'credit_card',
        }.get(self.payment_channel)
        selected = [name for name, instrument in instruments.items() if instrument]
        if expected and selected != [expected]:
            errors['payment_channel'] = _(
                '%(payment_channel)s requires only %(instrument)s.'
            ) % {
                'payment_channel': self.get_payment_channel_display(),
                'instrument': self._meta.get_field(expected).verbose_name,
            }

        owned = {'category': self.category if self.category_id else None, **instruments}
        for field, related in owned.items():
            if related and self.user_id and related.user_id != self.user_id:
                errors[field] = _('This selection must belong to the transaction owner.')

        if (
            self.category_id
            and self.category.transaction_type
            and self.category.transaction_type != self.transaction_type
        ):
            errors['category'] = _(
                'This category is available only for %(transaction_type)s transactions.'
            ) % {'transaction_type': self.category.get_transaction_type_display().lower()}

        if self.transaction_type == self.TransactionType.INCOME and self.payment_channel in {
            self.PaymentChannel.DEBIT_CARD,
            self.PaymentChannel.CREDIT_CARD,
        }:
            errors['payment_channel'] = _(
                'Income must be received in a bank account or by PIX.'
            )
        if (
            self.payment_channel == self.PaymentChannel.PIX
            and self.bank_account_id
            and not self.bank_account.pix_enabled
        ):
            errors['bank_account'] = _('PIX is disabled for this account.')
        if self.installments and self.installments > 1:
            if not self.is_credit_card:
                errors['installments'] = _(
                    'Installments are only available for credit cards.'
                )
            if self.is_fixed:
                errors['installments'] = _(
                    'A fixed transaction cannot use installments.'
                )
        if self.billing_override is not None and not self.is_credit_card:
            errors['billing_override'] = _(
                'Bill choice is only available for credit cards.'
            )
        if self.fixed_until:
            if not self.is_fixed:
                errors['fixed_until'] = _(
                    'Only fixed transactions can have an end date.'
                )
            elif self.date and (self.fixed_until.year, self.fixed_until.month) < (
                self.date.year,
                self.date.month,
            ):
                errors['fixed_until'] = _(
                    'The end month cannot precede the start month.'
                )
        if errors:
            raise ValidationError(errors)

    @property
    def transaction_date(self):
        """Read-only transition alias for projection consumers."""
        return self.date

    @property
    def is_credit_card(self):
        return self.payment_channel == self.PaymentChannel.CREDIT_CARD

    @property
    def payment_account(self):
        if self.bank_account_id:
            return self.bank_account
        if self.debit_card_id:
            return self.debit_card.account
        if self.credit_card_id:
            return self.credit_card.account
        return None

    @property
    def payment_name(self):
        instrument = self.bank_account or self.debit_card or self.credit_card
        return instrument.name if instrument else ''

    @property
    def payment_label(self):
        account = self.payment_account
        if self.bank_account_id and account:
            return f'{account.bank.name} > {account.name}'
        if account:
            return f'{account.bank.name} > {account.name} / {self.payment_name}'
        return self.payment_name

    @property
    def is_installment_plan(self):
        return self.installments > 1

    @property
    def installment_amount(self):
        if not self.is_installment_plan:
            return self.amount
        return (self.amount / self.installments).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

    def calendar_months_to(self, year, month):
        return (year - self.date.year) * 12 + (month - self.date.month)

    @property
    def billing_offset(self):
        if not self.is_credit_card or not self.credit_card_id:
            return 0
        statement_month = self.credit_card.statement_month(
            self.date, override=self.billing_override
        )
        return self.calendar_months_to(statement_month.year, statement_month.month)

    def months_from_start(self, year, month):
        return self.calendar_months_to(year, month) - self.billing_offset

    @property
    def last_fixed_offset(self):
        if not self.is_fixed or self.fixed_until is None:
            return None
        return max(0, self.calendar_months_to(self.fixed_until.year, self.fixed_until.month))

    @property
    def billed_month(self):
        index = self.date.year * 12 + self.date.month - 1 + self.billing_offset
        year, month = divmod(index, 12)
        if not date.min.year <= year <= date.max.year:
            return None
        return date(year, month + 1, 1)

    @property
    def payment_date(self):
        if not self.is_credit_card:
            return self.date
        billed = self.billed_month
        return self.credit_card.due_date_for(billed) if billed else None

    def amount_for_month(self, year, month):
        offset = self.months_from_start(year, month)
        if offset < 0:
            return ZERO
        if self.is_fixed:
            last_offset = self.last_fixed_offset
            return ZERO if last_offset is not None and offset > last_offset else self.amount
        if self.is_installment_plan:
            if offset >= self.installments:
                return ZERO
            if offset == self.installments - 1:
                return self.amount - self.installment_amount * (self.installments - 1)
            return self.installment_amount
        return self.amount if offset == 0 else ZERO

    def amount_through_month(self, year, month):
        offset = self.months_from_start(year, month)
        if offset < 0:
            return ZERO
        if self.is_fixed:
            if self.last_fixed_offset is not None:
                offset = min(offset, self.last_fixed_offset)
            return self.amount * (offset + 1)
        if self.is_installment_plan:
            paid = min(offset + 1, self.installments)
            return self.amount if paid == self.installments else self.installment_amount * paid
        return self.amount
