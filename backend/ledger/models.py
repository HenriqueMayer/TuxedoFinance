from collections import defaultdict
from dataclasses import replace
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from banking.models import BankAccount, CreditCard, DebitCard
from config import clock
from ledger import schedule
from ledger.categories import Category
from ledger.projection import ProjectionLimitExceeded, validate_occurrences

# The payment channels of a source that can require confirmation of each month.
CONFIRMATION_CHANNELS = ("ACCOUNT", "PIX", "DEBIT_CARD")
# The schedule rows of a source without R4 rows: (amount changes, overrides).
NO_SCHEDULE_ROWS = ((), ())


# The bits of the ``schedule_row_flags`` annotation (``with_schedule_flags``).
AMOUNT_ROWS_FLAG = 1
OVERRIDE_ROWS_FLAG = 2


class TransactionQuerySet(models.QuerySet):
    def with_schedule_flags(self):
        """Annotate ``schedule_row_flags``: the kinds of R4 rows of each transaction.

        The value is a sum of bits: ``AMOUNT_ROWS_FLAG`` for amount changes
        and ``OVERRIDE_ROWS_FLAG`` for month overrides. Only a commitment
        source (fixed, one installment) gets bits, because the engine ignores
        the rows of other sources. The two ``Exists`` probes are in the same
        SELECT, so they add no query. One integer column without a database
        converter costs less for each row than two boolean columns.
        ``attach_schedule_rows`` then loads only the rows of flagged
        transactions.
        """
        commitment = models.Q(is_fixed=True, installments=1)

        def flag(model, bit):
            rows = models.Exists(model.objects.filter(transaction=models.OuterRef("pk")))
            return models.Case(
                models.When(commitment & rows, then=models.Value(bit)), default=models.Value(0)
            )

        return self.annotate(
            schedule_row_flags=flag(ScheduleAmount, AMOUNT_ROWS_FLAG)
            + flag(OccurrenceOverride, OVERRIDE_ROWS_FLAG)
        )


def _wanted_rows(item):
    """Return ``(amounts, overrides)``: whether ``item`` can have each kind of R4 row.

    Without the ``with_schedule_flags`` annotation, both are True.
    """
    flags = item.__dict__.get("schedule_row_flags")
    if flags is None:
        return True, True
    return bool(flags & AMOUNT_ROWS_FLAG), bool(flags & OVERRIDE_ROWS_FLAG)


class Transaction(models.Model):
    MAX_INSTALLMENTS = 48

    class TransactionType(models.TextChoices):
        INCOME = "INCOME", gettext_lazy("Income")
        EXPENSE = "EXPENSE", gettext_lazy("Expense")

    class PaymentChannel(models.TextChoices):
        ACCOUNT = "ACCOUNT", gettext_lazy("Bank account")
        PIX = "PIX", gettext_lazy("PIX")
        DEBIT_CARD = "DEBIT_CARD", gettext_lazy("Debit card")
        CREDIT_CARD = "CREDIT_CARD", gettext_lazy("Credit card")

    class BillChoice(models.IntegerChoices):
        CURRENT = 0, gettext_lazy("Current bill")
        NEXT = 1, gettext_lazy("Next bill")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="transactions"
    )
    title = models.CharField(max_length=150)
    amount = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="transactions")
    payment_channel = models.CharField(max_length=20, choices=PaymentChannel.choices)
    bank_account = models.ForeignKey(
        BankAccount,
        on_delete=models.PROTECT,
        related_name="transactions",
        null=True,
        blank=True,
    )
    debit_card = models.ForeignKey(
        DebitCard,
        on_delete=models.PROTECT,
        related_name="transactions",
        null=True,
        blank=True,
    )
    credit_card = models.ForeignKey(
        CreditCard,
        on_delete=models.PROTECT,
        related_name="transactions",
        null=True,
        blank=True,
    )
    installments = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_INSTALLMENTS)],
    )
    installment_start = models.PositiveSmallIntegerField(
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
    reward_redemption = models.OneToOneField(
        "banking.RewardRedemption",
        on_delete=models.CASCADE,
        related_name="iof_transaction",
        null=True,
        blank=True,
        editable=False,
    )
    # R4: each month from confirmation_start (the first day of a reference
    # month) is expected until the owner confirms it. Only fixed sources with
    # one installment that do not use a credit card can require confirmation.
    requires_confirmation = models.BooleanField(default=False)
    confirmation_start = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TransactionQuerySet.as_manager()

    class Meta:
        ordering = ["-date", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="ledger_amount_gt_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    installment_start__gte=1, installment_start__lte=models.F("installments")
                ),
                name="ledger_installment_start_range",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        payment_channel__in=["ACCOUNT", "PIX"],
                        bank_account__isnull=False,
                        debit_card__isnull=True,
                        credit_card__isnull=True,
                    )
                    | models.Q(
                        payment_channel="DEBIT_CARD",
                        bank_account__isnull=True,
                        debit_card__isnull=False,
                        credit_card__isnull=True,
                    )
                    | models.Q(
                        payment_channel="CREDIT_CARD",
                        bank_account__isnull=True,
                        debit_card__isnull=True,
                        credit_card__isnull=False,
                    )
                ),
                name="ledger_coherent_payment_instrument",
            ),
            models.CheckConstraint(
                condition=models.Q(requires_confirmation=False)
                | models.Q(confirmation_start__isnull=False),
                name="ledger_confirmation_has_start",
            ),
            models.CheckConstraint(
                condition=models.Q(requires_confirmation=False)
                | models.Q(
                    is_fixed=True, installments=1, payment_channel__in=CONFIRMATION_CHANNELS
                ),
                name="ledger_confirmation_scope",
            ),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_transaction_type_display()})"

    @property
    def display_title(self):
        return _("IOF on reward redemption") if self.reward_redemption_id else self.title

    @property
    def native_currency(self):
        account = self.payment_account
        return account.currency if account else ""

    def clean(self):
        errors = {}
        instruments = {
            "bank_account": self.bank_account if self.bank_account_id else None,
            "debit_card": self.debit_card if self.debit_card_id else None,
            "credit_card": self.credit_card if self.credit_card_id else None,
        }
        expected = {
            self.PaymentChannel.ACCOUNT: "bank_account",
            self.PaymentChannel.PIX: "bank_account",
            self.PaymentChannel.DEBIT_CARD: "debit_card",
            self.PaymentChannel.CREDIT_CARD: "credit_card",
        }.get(self.payment_channel)
        selected = [name for name, instrument in instruments.items() if instrument]
        if expected and selected != [expected]:
            errors["payment_channel"] = _("%(payment_channel)s requires only %(instrument)s.") % {
                "payment_channel": self.get_payment_channel_display(),
                "instrument": self._meta.get_field(expected).verbose_name,
            }

        owned = {"category": self.category if self.category_id else None, **instruments}
        for field, related in owned.items():
            if related and self.user_id and related.user_id != self.user_id:
                errors[field] = _("This selection must belong to the transaction owner.")

        if (
            self.category_id
            and self.category.transaction_type
            and self.category.transaction_type != self.transaction_type
        ):
            errors["category"] = _(
                "This category is available only for %(transaction_type)s transactions."
            ) % {"transaction_type": self.category.get_transaction_type_display().lower()}

        if self.transaction_type == self.TransactionType.INCOME and self.payment_channel in {
            self.PaymentChannel.DEBIT_CARD,
            self.PaymentChannel.CREDIT_CARD,
        }:
            errors["payment_channel"] = _("Income must be received in a bank account or by PIX.")
        if (
            self.payment_channel == self.PaymentChannel.PIX
            and self.bank_account_id
            and not self.bank_account.pix_enabled
        ):
            errors["bank_account"] = _("PIX is disabled for this account.")
        if self.installments and self.installments > 1:
            if not self.is_credit_card:
                errors["installments"] = _("Installments are only available for credit cards.")
            if self.is_fixed:
                errors["installments"] = _("A fixed transaction cannot use installments.")
        if (
            self.installment_start
            and self.installments
            and self.installment_start > self.installments
        ):
            errors["installment_start"] = _(
                "The first tracked installment cannot exceed the installment count."
            )
        if (
            self.installment_start
            and self.installment_start > 1
            and (not self.is_credit_card or self.is_fixed)
        ):
            errors["installment_start"] = _(
                "A later starting installment requires a non-recurring credit-card purchase."
            )
        if self.billing_override is not None and not self.is_credit_card:
            errors["billing_override"] = _("Bill choice is only available for credit cards.")
        if self.fixed_until:
            if not self.is_fixed:
                errors["fixed_until"] = _("Only fixed transactions can have an end date.")
            elif self.date and (self.fixed_until.year, self.fixed_until.month) < (
                self.date.year,
                self.date.month,
            ):
                errors["fixed_until"] = _("The end month cannot precede the start month.")
        if self.confirmation_start is not None and self.confirmation_start.day != 1:
            # SQLite cannot check the day in a database constraint outside
            # Django connections; CardInvoice.reference_month has the same rule.
            errors["confirmation_start"] = _("Use the first day of the month.")
        if self.requires_confirmation:
            if not self.can_require_confirmation:
                errors["requires_confirmation"] = _(
                    "Confirmation is available only for monthly recurring transactions paid from "
                    "an account, by PIX or by debit card."
                )
            elif self.confirmation_start is None:
                errors["confirmation_start"] = _("Choose the first month to confirm.")
        account = self.payment_account
        if account and account.predates_opening(self.date):
            errors["date"] = _("The transaction cannot precede the account opening balance date.")
        try:
            validate_occurrences(self)
        except ProjectionLimitExceeded as error:
            errors["date"] = error
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
        return instrument.name if instrument else ""

    @property
    def payment_label(self):
        account = self.payment_account
        if self.bank_account_id and account:
            return f"{account.bank.name} > {account.name}"
        if account:
            return f"{account.bank.name} > {account.name} / {self.payment_name}"
        return self.payment_name

    @property
    def is_installment_plan(self):
        return self.installments > 1

    @property
    def is_commitment_source(self):
        """Return whether amount changes and month overrides apply: a fixed source with one installment."""
        return self.is_fixed and self.installments == 1

    @property
    def can_require_confirmation(self):
        """Return whether the source can require confirmation: a commitment source without a credit card."""
        return self.is_commitment_source and self.payment_channel in CONFIRMATION_CHANNELS

    # The schedule helpers below are thin wrappers over the rule functions of
    # the occurrence engine, transactions.schedule. Each one calculates one
    # month directly, without a visit to the earlier months. The exception is
    # category_allocations_for_month: for a split installment plan it replays
    # the split of each earlier installment (at most 47; a legacy fixed row
    # with installments replays once per month of its offset). The readers in
    # dashboard, planning and sandbox use schedule.expand; the helpers stay for
    # the banking views, invoice credits and tests
    # .

    @property
    def installment_amount(self):
        return schedule.installment_amount(self.amount, self.installments)

    @property
    def first_installment_amount(self):
        return schedule.first_installment_amount(self.amount, self.installments)

    def calendar_months_to(self, year, month):
        return schedule.months_between(self.date, year, month)

    @property
    def billing_offset(self):
        if not self.is_credit_card or not self.credit_card_id:
            return 0
        return schedule.billing_offset(
            self.date, self.credit_card.closing_day, self.billing_override
        )

    def months_from_start(self, year, month):
        return schedule.months_between(self.date, year, month) - self.billing_offset

    @property
    def last_fixed_offset(self):
        return schedule.last_fixed_offset(self.is_fixed, self.date, self.fixed_until)

    @property
    def billed_month(self):
        return schedule.offset_month(self.date, self.billing_offset)

    @property
    def payment_date(self):
        if not self.is_credit_card:
            return self.date
        billed = self.billed_month
        return self.credit_card.due_date_for(billed) if billed else None

    def _commitment_source(self):
        """Return the engine source when amount changes or overrides apply, otherwise None."""
        if not self.is_commitment_source:
            return None
        amounts, overrides = self.schedule_rows()
        if not amounts and not overrides:
            return None
        return self.schedule_source()

    def amount_for_month(self, year, month):
        source = self._commitment_source()
        if source is not None:
            found = schedule.expand((source,), schedule.Window.months(date(year, month, 1)))
            return found[0].amount if found else schedule.ZERO
        is_fixed = self.is_fixed
        return schedule.amount_at(
            self.months_from_start(year, month),
            self.amount,
            is_fixed,
            self.last_fixed_offset if is_fixed else None,
            self.installments,
            self.installment_start,
        )

    def amount_through_month(self, year, month):
        source = self._commitment_source()
        if source is not None:
            first = self.billed_month
            last = date(year, month, 1)
            if first is None or last < first:
                return schedule.ZERO
            found = schedule.expand((source,), schedule.Window.months(first, last))
            return sum((occurrence.amount for occurrence in found), schedule.ZERO)
        is_fixed = self.is_fixed
        return schedule.amount_through(
            self.months_from_start(year, month),
            self.amount,
            is_fixed,
            self.last_fixed_offset if is_fixed else None,
            self.installments,
            self.installment_start,
        )

    @staticmethod
    def _split_amount(amount, capacities):
        return schedule.split_amount(amount, capacities)

    def category_allocations_for(self, amount):
        """Allocate one event with deterministic largest-remainder cents."""
        rows = list(self.splits.all()) if self.pk else []
        if not rows:
            return [(self.category, amount)]
        return [
            (row.category, value)
            for row, value in zip(
                rows, schedule.split_amount(amount, [row.amount for row in rows]), strict=False
            )
        ]

    def category_allocations_for_month(self, year, month):
        amount = self.amount_for_month(year, month)
        if not self.is_installment_plan or not amount:
            return self.category_allocations_for(amount)
        rows = list(self.splits.all()) if self.pk else []
        if not rows:
            return [(self.category, amount)]
        values = schedule.installment_split(
            self.months_from_start(year, month),
            [row.amount for row in rows],
            self.first_installment_amount,
            self.installment_amount,
        )
        return [(row.category, value) for row, value in zip(rows, values, strict=False)]

    def schedule_rows(self):
        """Return ``(amounts, overrides)``: the R4 rows of this source as engine values.

        ``amounts`` holds ``(effective_month, amount)`` pairs and ``overrides``
        holds ``schedule.Override`` values, both in month order. The rows come
        from ``attach_schedule_rows``. Without attached rows, a saved
        commitment source reads them with at most two queries, once for each
        instance; the ``with_schedule_flags`` annotation skips a query for a
        source without rows. A row of another owner raises a
        ``ValidationError``, as in ``attach_schedule_rows``. An unsaved
        transaction and a source to which the rows do not apply have no rows.
        """
        rows = self.__dict__.get("_schedule_rows")
        if rows is not None:
            return rows
        if self.id is None or self._state.adding or not self.is_commitment_source:
            # Not cached: a form can make the source fixed before it reads the rows.
            return NO_SCHEDULE_ROWS
        wants_amounts, wants_overrides = _wanted_rows(self)
        amounts = overrides = ()
        if wants_amounts:
            amounts = tuple(_owned_values(self, ScheduleAmount, ("effective_month", "amount")))
        if wants_overrides:
            overrides = tuple(
                schedule.Override(*values)
                for values in _owned_values(
                    self, OccurrenceOverride, ("month", "status", "amount", "date")
                )
            )
        rows = (amounts, overrides) if amounts or overrides else NO_SCHEDULE_ROWS
        self._schedule_rows = rows
        return rows

    def clear_schedule_rows(self):
        """Forget the loaded R4 rows, so that the next read loads them again."""
        self.__dict__.pop("_schedule_rows", None)

    def schedule_source(self, *, splits=False):
        """Return the occurrence-engine value of this transaction (``schedule.ScheduleSource``).

        The value uses the loaded instrument objects. ``splits=True`` adds the
        split capacities for ``schedule.expand(..., allocations=True)``; it
        reads ``self.splits``, so prefetch them for many transactions. An
        unsaved transaction has no split rows. The R4 fields come from
        ``schedule_rows()`` and from the confirmation setting.
        """
        account = self.payment_account
        card = self.credit_card if self.is_credit_card and self.credit_card_id else None
        # ``id`` is the primary key of both models; the ``pk`` property is
        # slower, and synchronization calls this for every source.
        instrument = schedule.instrument(
            self.payment_channel,
            self.bank_account_id or self.debit_card_id or self.credit_card_id,
            account.id if account is not None else None,
            card.closing_day if card is not None else None,
            card.due_day if card is not None else None,
        )
        capacities = None
        if splits:
            capacities = (
                tuple((row.category_id, row.amount) for row in self.splits.all()) if self.id else ()
            )
        amounts, overrides = self.schedule_rows()
        confirmation = self.confirmation_start if self.requires_confirmation else None
        if amounts or overrides or confirmation is not None:
            return schedule.ScheduleSource(
                schedule.TRANSACTION,
                self.id,
                self.date,
                self.amount,
                account.currency if account is not None else "",
                self.transaction_type,
                instrument,
                self.is_fixed,
                self.fixed_until,
                self.installments,
                self.installment_start,
                self.billing_override,
                self.category_id,
                capacities,
                amounts,
                overrides,
                confirmation,
            )
        return schedule.ScheduleSource(
            schedule.TRANSACTION,
            self.id,
            self.date,
            self.amount,
            account.currency if account is not None else "",
            self.transaction_type,
            instrument,
            self.is_fixed,
            self.fixed_until,
            self.installments,
            self.installment_start,
            self.billing_override,
            self.category_id,
            capacities,
        )


class TransactionSplit(models.Model):
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="splits")
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="transaction_splits"
    )
    amount = models.DecimalField(
        max_digits=16, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="ledger_split_amount_gt_zero"
            ),
            models.UniqueConstraint(
                fields=["transaction", "category"], name="ledger_unique_split_category"
            ),
        ]

    def clean(self):
        if self.transaction_id and self.category_id:
            if self.category.user_id != self.transaction.user_id:
                raise ValidationError(
                    {"category": _("This category must belong to the transaction owner.")}
                )
            if (
                self.category.transaction_type
                and self.category.transaction_type != self.transaction.transaction_type
            ):
                raise ValidationError(
                    {"category": _("Choose a category compatible with the transaction type.")}
                )


def _month_text(month):
    return date_format(month, "YEAR_MONTH_FORMAT")


def _source_errors(item):
    """Return the error of a source to which amount changes and overrides do not apply, or None."""
    if item.installments > 1:
        return _("Installment plans keep their amounts.")
    if not item.is_fixed or item.reward_redemption_id:
        return _("Only monthly recurring transactions have a monthly schedule.")
    return None


def _first_of_month_error(value):
    return None if value is None or value.day == 1 else _("Use the first day of the month.")


class ScheduleAmount(models.Model):
    """An amount change of a recurring source.

    ``amount`` applies from ``effective_month`` (the first day of a reference
    month) until the next row of the source. ``Transaction.amount`` applies
    before the first row. ``user`` repeats the owner of the transaction, so
    the ledger-input receiver and the owner checks can read it.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="schedule_amounts"
    )
    transaction = models.ForeignKey(
        Transaction, on_delete=models.CASCADE, related_name="schedule_amounts"
    )
    effective_month = models.DateField()
    amount = models.DecimalField(
        max_digits=16, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # transaction_id, not transaction: ordering by the relation would join
        # Transaction for its own ordering.
        ordering = ["transaction_id", "effective_month"]
        constraints = [
            models.UniqueConstraint(
                fields=["transaction", "effective_month"],
                name="ledger_unique_schedule_amount_month",
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="ledger_schedule_amount_gt_zero"
            ),
        ]

    def clean(self):
        errors = {}
        month_error = _first_of_month_error(self.effective_month)
        if month_error:
            errors["effective_month"] = month_error
        if self.transaction_id is None:
            if errors:
                raise ValidationError(errors)
            return
        item = self.transaction
        # Validate against the stored rows, not rows that the instance loaded earlier.
        item.clear_schedule_rows()
        if self.user_id != item.user_id:
            errors["transaction"] = _("This selection must belong to the transaction owner.")
        source_error = _source_errors(item)
        if source_error:
            errors["transaction"] = source_error
        if errors or self.effective_month is None:
            if errors:
                raise ValidationError(errors)
            return
        source = item.schedule_source()
        first = schedule.amount_steps(replace(source, amounts=()))[0][0]
        index = schedule.month_index(self.effective_month)
        if index <= schedule.month_index(first):
            errors["effective_month"] = _(
                "Choose a month after the first month of this schedule. To change every month, "
                "edit the transaction."
            )
        else:
            last = schedule.last_fixed_offset(True, item.date, item.fixed_until)
            if last is not None and index > schedule.month_index(first) + last:
                errors["effective_month"] = _("This month is after the end of the schedule.")
        if not errors and self.amount is not None:
            others = tuple(row for row in source.amounts if row[0] != self.effective_month)
            if self.amount == schedule.scheduled_amount(
                replace(source, amounts=others), self.effective_month
            ):
                errors["amount"] = _("This amount already applies from that month.")
        if errors:
            raise ValidationError(errors)


class OccurrenceOverride(models.Model):
    """The change of one month of a recurring source.

    ``month`` is the first day of the reference month: the statement month
    for a credit card. A source has at most one override for each month; a
    new action replaces it, and "undo" deletes it.

    - ``SKIPPED``: the month has no occurrence.
    - ``ADJUSTED``: ``amount`` or ``date`` replaces the scheduled value of the
      month; the date stays inside the month.
    - ``CONFIRMED``: the owner confirmed the month of a source that requires
      confirmation, with the actual amount and date. The date can be in a
      later month, but not after today.

    A source with a credit card has no ``date``: its statement does not move.
    """

    class Status(models.TextChoices):
        SKIPPED = schedule.SKIPPED, gettext_lazy("Skipped")
        ADJUSTED = schedule.ADJUSTED, gettext_lazy("Adjusted")
        CONFIRMED = schedule.CONFIRMED, gettext_lazy("Confirmed")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="occurrence_overrides"
    )
    transaction = models.ForeignKey(
        Transaction, on_delete=models.CASCADE, related_name="occurrence_overrides"
    )
    month = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices)
    amount = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["transaction_id", "month"]
        constraints = [
            models.UniqueConstraint(
                fields=["transaction", "month"], name="ledger_unique_override_month"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["SKIPPED", "ADJUSTED", "CONFIRMED"]),
                name="ledger_override_status_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(amount__isnull=True) | models.Q(amount__gt=0),
                name="ledger_override_amount_gt_zero",
            ),
            models.CheckConstraint(
                condition=~models.Q(status="SKIPPED")
                | models.Q(amount__isnull=True, date__isnull=True),
                name="ledger_override_skip_has_no_values",
            ),
            models.CheckConstraint(
                condition=~models.Q(status="ADJUSTED")
                | models.Q(amount__isnull=False)
                | models.Q(date__isnull=False),
                name="ledger_override_adjust_has_a_value",
            ),
        ]

    def scheduled_occurrence(self):
        """Return the occurrence of ``month`` without this month's override and confirmation, or None."""
        source = self.transaction.schedule_source()
        source = replace(
            source,
            overrides=tuple(row for row in source.overrides if row.month != self.month),
            confirmation_start=None,
        )
        found = schedule.expand((source,), schedule.Window.months(self.month))
        return found[0] if found else None

    def clean(self):
        errors = {}
        month_error = _first_of_month_error(self.month)
        if month_error:
            errors["month"] = month_error
        if self.transaction_id is None:
            if errors:
                raise ValidationError(errors)
            return
        item = self.transaction
        # Validate against the stored rows, not rows that the instance loaded earlier.
        item.clear_schedule_rows()
        if self.user_id != item.user_id:
            errors["transaction"] = _("This selection must belong to the transaction owner.")
        source_error = _source_errors(item)
        if source_error:
            errors["transaction"] = source_error
        if errors or self.month is None:
            if errors:
                raise ValidationError(errors)
            return
        scheduled = self.scheduled_occurrence()
        if scheduled is None:
            raise ValidationError({"month": _("This month has no occurrence of the schedule.")})
        month = _month_text(self.month)
        if self.date is not None and item.is_credit_card:
            errors["date"] = _("A card purchase keeps its statement; only its amount can change.")
        elif self.status == self.Status.ADJUSTED:
            if self.date is not None and self.date.replace(day=1) != self.month:
                errors["date"] = _("The date must be in %(month)s.") % {"month": month}
            if (self.amount is None or self.amount == scheduled.amount) and (
                self.date is None or self.date == scheduled.cash_date
            ):
                # On the amount field: the constraint of an adjustment without
                # values then adds no second, generic message.
                errors["amount"] = _("Change the amount or the date, or cancel.")
        elif self.status == self.Status.CONFIRMED:
            if not item.requires_confirmation or item.confirmation_start is None:
                errors["status"] = _("This transaction does not ask for confirmation.")
            elif self.month < item.confirmation_start:
                errors["month"] = _("This month is before the first month to confirm.")
            else:
                # The services pass their ``today``; other callers use the financial date.
                today = getattr(self, "validation_today", None) or clock.today()
                when = scheduled.cash_date if self.date is None else self.date
                # A month after today has no valid confirmation date.
                if when > today or self.month > today:
                    errors["date"] = _("A confirmation date cannot be in the future.")
                elif when < self.month:
                    errors["date"] = _("The confirmation date cannot precede %(month)s.") % {
                        "month": month
                    }
        if self.date is not None and "date" not in errors:
            account = item.payment_account
            if account and account.predates_opening(self.date):
                errors["date"] = _(
                    "The transaction cannot precede the account opening balance date."
                )
        if errors:
            raise ValidationError(errors)

    @property
    def override(self):
        """Return the engine value of this row (``schedule.Override``)."""
        return schedule.Override(self.month, self.status, self.amount, self.date)


def _schedule_owner_error():
    return ValidationError(
        _("A schedule change of a transaction belongs to another owner."), code="owner"
    )


def _owned_values(item, model, fields):
    """Return the ``fields`` tuples of the ``model`` rows of ``item``; raise for a row of another owner."""
    values = []
    for row_user_id, *row in model.objects.filter(transaction_id=item.id).values_list(
        "user_id", *fields
    ):
        if row_user_id != item.user_id:
            raise _schedule_owner_error()
        values.append(tuple(row))
    return values


def attach_schedule_rows(items, *, user_id=None, error=None):
    """Load the R4 rows of ``items`` and attach them for ``Transaction.schedule_rows``.

    Only items that ``with_schedule_flags`` flagged, or that have no flag,
    are loaded: at most one query for amount changes and one for overrides,
    and no query when no item is flagged. Every item gets its rows, an empty
    pair for most. A row whose owner differs from the owner of its
    transaction, or from ``user_id``, raises ``error()`` (a ``ValidationError``
    by default; ``queries`` passes ``OwnershipError``). Return the items.
    """
    items = list(items)
    wanted = {"amounts": set(), "overrides": set()}
    owners = set()
    for item in items:
        if item.id is None or item._state.adding:
            continue
        owners.add(item.user_id)
        wants_amounts, wants_overrides = _wanted_rows(item)
        if wants_amounts:
            wanted["amounts"].add(item.id)
        if wants_overrides:
            wanted["overrides"].add(item.id)
    by_item = {"amounts": defaultdict(list), "overrides": defaultdict(list)}
    loads = (
        ("amounts", ScheduleAmount, ("effective_month", "amount"), tuple),
        (
            "overrides",
            OccurrenceOverride,
            ("month", "status", "amount", "date"),
            lambda values: schedule.Override(*values),
        ),
    )
    owner_of = {item.id: item.user_id for item in items if item.id is not None}
    for name, model, fields, value in loads:
        ids = wanted[name]
        if not ids:
            continue
        rows = model.objects.all()
        # One owner: select by owner, so the query has no long id list.
        rows = (
            rows.filter(transaction__user_id=next(iter(owners)))
            if len(owners) == 1
            else rows.filter(transaction_id__in=ids)
        )
        for transaction_id, row_user_id, *values in rows.values_list(
            "transaction_id", "user_id", *fields
        ):
            if transaction_id not in ids:
                continue
            if row_user_id != owner_of[transaction_id] or (
                user_id is not None and row_user_id != user_id
            ):
                raise (error or _schedule_owner_error)()
            by_item[name][transaction_id].append(value(values))
    amount_rows, override_rows = by_item["amounts"], by_item["overrides"]
    for item in items:
        if item.id in amount_rows or item.id in override_rows:
            item._schedule_rows = (
                tuple(amount_rows.get(item.id, ())),
                tuple(override_rows.get(item.id, ())),
            )
        else:
            item._schedule_rows = NO_SCHEDULE_ROWS
    return items


class LedgerSyncState(models.Model):
    """The last ledger synchronization of one user.

    ``transactions.services.sync_user_ledger`` writes this row. ``synced_on``
    is the financial date of a synchronization as of that date. It is null
    when the ledger is stale: a ledger input changed after the
    synchronization, or the synchronization used another date.
    ``horizon_end`` is the last date that the synchronization projected.
    ``rules_version`` is the ``transactions.services.LEDGER_RULES_VERSION`` of
    the code that synchronized; a state of other rules is not current.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ledger_sync_state"
    )
    synced_on = models.DateField(null=True)
    horizon_end = models.DateField(null=True)
    rules_version = models.PositiveSmallIntegerField(default=0)


# Statement-import models live in their own module and belong to this app.
from ledger.statements import ExternalStatementIdentity, ImportBatch, ImportedRow  # noqa: E402, F401
