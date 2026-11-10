from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, DecimalField, F, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils.translation import gettext

from banking.models import (
    BankAccount,
    BankMovement,
    BankTransfer,
    ExchangeRate,
    LoyaltyEntry,
    LoyaltyProgram,
    RewardRedemption,
)
from config import clock

ZERO = Decimal("0.00")
CENTS = Decimal("0.01")


class MissingExchangeRate(LookupError):
    pass


def opening_balance_as_of(account, as_of):
    """Return the opening balance that applies on ``as_of``.

    An undated legacy opening always applies. A dated opening applies from its
    date, so it does not appear in periods before that date.
    """
    return (
        account.opening_balance
        if account.opening_date is None or account.opening_date <= as_of
        else ZERO
    )


def account_balance(account, as_of=None):
    as_of = as_of or clock.today()
    queryset = account.movements.filter(effective_date__lte=as_of)
    amount_field = DecimalField(max_digits=16, decimal_places=2)
    movement_total = queryset.aggregate(
        total=Coalesce(
            Sum(
                Case(
                    When(direction=BankMovement.Direction.CREDIT, then=F("amount")),
                    default=-F("amount"),
                    output_field=amount_field,
                )
            ),
            Value(ZERO),
            output_field=amount_field,
        )
    )["total"]
    return opening_balance_as_of(account, as_of) + movement_total


def account_balances(user, as_of=None):
    """Read all native balances with one grouped movement query."""
    as_of = as_of or clock.today()
    amount_field = DecimalField(max_digits=20, decimal_places=2)
    movements = BankMovement.objects.filter(user=user, effective_date__lte=as_of)
    totals = dict(
        movements.order_by()
        .values("account_id")
        .annotate(
            total=Sum(
                Case(
                    When(direction=BankMovement.Direction.CREDIT, then=F("amount")),
                    default=-F("amount"),
                    output_field=amount_field,
                )
            )
        )
        .values_list("account_id", "total")
    )
    return [
        {
            "account": account,
            # SQLite returns a sum with more decimal places; amounts are whole cents.
            "balance": (
                opening_balance_as_of(account, as_of) + totals.get(account.pk, ZERO)
            ).quantize(CENTS),
        }
        for account in BankAccount.objects.filter(user=user).select_related("bank")
    ]


def movements_before_opening(user):
    """Expose existing baseline conflicts for review without rewriting history."""
    return (
        BankMovement.objects.filter(
            user=user,
            account__user=user,
            account__opening_date__isnull=False,
            effective_date__lt=F("account__opening_date"),
        )
        .select_related("account__bank")
        .order_by("effective_date", "pk")
    )


def create_movement(
    *,
    user,
    account,
    direction,
    kind,
    amount,
    effective_date,
    description="",
    source_key="",
    **links,
):
    movement = BankMovement(
        user=user,
        account=account,
        direction=direction,
        kind=kind,
        amount=amount,
        effective_date=effective_date,
        description=description,
        source_key=source_key,
        **links,
    )
    movement.full_clean()
    movement.save()
    return movement


@transaction.atomic
def sync_loyalty_entry_funding(entry):
    """Synchronize the immediate cash side of a points purchase."""
    entry.full_clean()
    wants_movement = (
        entry.kind == LoyaltyEntry.Kind.PURCHASE and entry.funding_account_id is not None
    )
    if wants_movement:
        movement, _ = BankMovement.objects.update_or_create(
            user=entry.user,
            source_key=f"loyalty-entry:{entry.pk}",
            defaults={
                "account": entry.funding_account,
                "direction": BankMovement.Direction.DEBIT,
                "kind": BankMovement.Kind.EXPENSE,
                "amount": entry.cash_amount,
                "effective_date": entry.date,
                "description": gettext("Points purchase: %(program)s")
                % {
                    "program": entry.program.name,
                },
                "invoice": None,
                "transfer": None,
            },
        )
        if entry.funding_movement_id != movement.pk:
            entry.funding_movement = movement
            entry.save(update_fields=["funding_movement"])
    elif entry.funding_movement_id:
        movement = entry.funding_movement
        entry.funding_movement = None
        entry.save(update_fields=["funding_movement"])
        movement.delete()
    return entry


@transaction.atomic
def cleanup_loyalty_entry_funding(entry):
    movement = entry.funding_movement
    if movement:
        entry.funding_movement = None
        entry.save(update_fields=["funding_movement"])
        movement.delete()


@transaction.atomic
def create_transfer(
    *, user, source_account, destination_account, source_amount, destination_amount, date, notes=""
):
    account_ids = sorted([source_account.pk, destination_account.pk])
    locked = {
        account.pk: account
        for account in BankAccount.objects.select_for_update().filter(
            user=user,
            pk__in=account_ids,
        )
    }
    if len(locked) != len(set(account_ids)):
        raise ValidationError(gettext("One or more transfer accounts no longer exist."))
    transfer = BankTransfer(
        user=user,
        source_account=locked[source_account.pk],
        destination_account=locked[destination_account.pk],
        source_amount=source_amount,
        destination_amount=destination_amount,
        date=date,
        notes=notes,
    )
    transfer.full_clean()
    if transfer.source_account.currency != transfer.destination_account.currency:
        transfer.fx_source_currency = transfer.source_account.currency
        transfer.fx_target_currency = transfer.destination_account.currency
        transfer.fx_rate = (destination_amount / source_amount).quantize(Decimal("0.00000001"))
        transfer.fx_effective_date = date
        transfer.fx_snapshot_status = BankTransfer.FxSnapshotStatus.CAPTURED
    transfer.save()
    # Ledger labels are bounded summaries; the transfer keeps the full notes
    # (including imported statement evidence) for review and undo checks.
    movement_description = notes[: BankMovement._meta.get_field("description").max_length]
    create_movement(
        user=user,
        account=transfer.source_account,
        direction=BankMovement.Direction.DEBIT,
        kind=BankMovement.Kind.TRANSFER,
        amount=source_amount,
        effective_date=date,
        description=movement_description,
        transfer=transfer,
    )
    create_movement(
        user=user,
        account=transfer.destination_account,
        direction=BankMovement.Direction.CREDIT,
        kind=BankMovement.Kind.TRANSFER,
        amount=destination_amount,
        effective_date=date,
        description=movement_description,
        transfer=transfer,
    )
    return transfer


def _locked_transfer(user, pk):
    transfer = BankTransfer.objects.select_for_update().get(user=user, pk=pk)
    movements = list(transfer.movements.select_for_update().order_by("pk"))
    if transfer.statement_provenance.exists() or any(
        movement.statement_matches.exists() for movement in movements
    ):
        raise ValidationError(
            gettext(
                "This transfer is linked to a bank statement. Resolve its import or reconciliation before correcting it."
            )
        )
    if (
        transfer.source_account.user_id != user.pk
        or transfer.destination_account.user_id != user.pk
        or len(movements) != 2
        or {row.direction for row in movements} != {"CREDIT", "DEBIT"}
        or any(
            row.user_id != user.pk
            or row.account.user_id != user.pk
            or row.kind != BankMovement.Kind.TRANSFER
            for row in movements
        )
    ):
        raise ValidationError(
            gettext(
                "The transfer movement pair is inconsistent. Review its sources before correcting it."
            )
        )
    return transfer, movements


@transaction.atomic
def update_transfer(
    *,
    user,
    transfer,
    source_account,
    destination_account,
    source_amount,
    destination_amount,
    date,
    notes="",
):
    """Correct both cash legs together; notes alone retain captured FX evidence."""
    current, movements = _locked_transfer(user, transfer.pk)
    account_ids = {source_account.pk, destination_account.pk}
    accounts = {
        row.pk: row
        for row in BankAccount.objects.select_for_update()
        .filter(
            user=user,
            pk__in=account_ids,
        )
        .order_by("pk")
    }
    if set(accounts) != account_ids:
        raise ValidationError(gettext("One or more transfer accounts no longer exist."))
    changed = (
        current.source_account_id,
        current.destination_account_id,
        current.source_amount,
        current.destination_amount,
        current.date,
    ) != (source_account.pk, destination_account.pk, source_amount, destination_amount, date)
    current.source_account = accounts[source_account.pk]
    current.destination_account = accounts[destination_account.pk]
    current.source_amount, current.destination_amount = source_amount, destination_amount
    current.date, current.notes = date, notes
    current.full_clean()
    if changed:
        current.fx_source_rate = None
        current.fx_rate = None
        current.fx_source_currency = current.fx_target_currency = ""
        current.fx_effective_date = None
        current.fx_snapshot_status = BankTransfer.FxSnapshotStatus.UNKNOWN
        if current.source_account.currency != current.destination_account.currency:
            current.fx_rate = (Decimal(destination_amount) / Decimal(source_amount)).quantize(
                Decimal("0.00000001")
            )
            current.fx_source_currency = current.source_account.currency
            current.fx_target_currency = current.destination_account.currency
            current.fx_effective_date = date
            current.fx_snapshot_status = BankTransfer.FxSnapshotStatus.CAPTURED
    current.full_clean()
    current.save()
    for movement in movements:
        debit = movement.direction == BankMovement.Direction.DEBIT
        movement.account = current.source_account if debit else current.destination_account
        movement.amount = source_amount if debit else destination_amount
        movement.effective_date = date
        movement.description = notes[: BankMovement._meta.get_field("description").max_length]
        movement.full_clean()
        movement.save()
    return current


@transaction.atomic
def delete_transfer(*, user, transfer):
    """Undo both legs, or leave the complete operation untouched on failure."""
    current, movements = _locked_transfer(user, transfer.pk)
    for movement in movements:
        movement.delete()
    current.delete()


def latest_exchange_rate(user, from_currency, to_currency, as_of=None):
    if from_currency == to_currency:
        return None
    as_of = as_of or clock.today()
    return (
        ExchangeRate.objects.filter(
            user=user,
            from_currency=from_currency,
            to_currency=to_currency,
            effective_date__lte=as_of,
        )
        .order_by("-effective_date", "-created_at")
        .first()
    )


def convert(user, amount, from_currency, to_currency, as_of=None):
    amount = Decimal(amount)
    if from_currency == to_currency:
        return amount
    direct = latest_exchange_rate(user, from_currency, to_currency, as_of)
    if direct:
        return amount * direct.rate
    inverse = latest_exchange_rate(user, to_currency, from_currency, as_of)
    if inverse:
        return amount / inverse.rate
    raise MissingExchangeRate(
        gettext("No %(from_currency)s/%(to_currency)s exchange rate is available as of %(date)s.")
        % {
            "from_currency": from_currency,
            "to_currency": to_currency,
            "date": as_of or clock.today(),
        }
    )


class ConversionContext:
    """Reuse presentation rates only for one user's current request or calculation.

    Posting and captured historical evidence continue to use their existing
    services. Keeping original inverse rates preserves Decimal division exactly.
    """

    def __init__(self, user, base_currency=None):
        from accounts.models import UserPreference

        self.user = user
        self.user_id = user.pk
        self.base_currency = (
            base_currency
            if base_currency is not None
            else UserPreference.for_user(user).base_currency
        )
        self.today = clock.today()
        self._rates = {}

    def check_user(self, user):
        if user.pk != self.user_id:
            raise ValueError("A conversion context belongs to exactly one user.")
        return self

    def _rate(self, source, target, as_of):
        key = (source, target, as_of)
        if key not in self._rates:
            self._rates[key] = latest_exchange_rate(self.user, source, target, as_of)
        return self._rates[key]

    def convert(self, amount, from_currency, to_currency=None, as_of=None):
        amount = Decimal(amount)
        to_currency = self.base_currency if to_currency is None else to_currency
        if from_currency == to_currency:
            return amount
        as_of = self.today if as_of is None else as_of
        direct = self._rate(from_currency, to_currency, as_of)
        if direct is not None:
            return amount * direct.rate
        inverse = self._rate(to_currency, from_currency, as_of)
        if inverse is not None:
            return amount / inverse.rate
        raise MissingExchangeRate(
            gettext(
                "No %(from_currency)s/%(to_currency)s exchange rate is available as of %(date)s."
            )
            % {"from_currency": from_currency, "to_currency": to_currency, "date": as_of}
        )


def _iof_category(user):
    from ledger.categories import Category

    # IOF is the same acronym in both locales. Never reclassify an existing
    # income category; reuse a compatible name or its first available suffix.
    index = 1
    while True:
        name = "IOF" if index == 1 else f"IOF ({index})"
        category, _ = Category.objects.get_or_create(
            user=user,
            name=name,
            defaults={"transaction_type": "EXPENSE"},
        )
        if category.transaction_type != "INCOME":
            return category
        index += 1


def sync_redemption_iof_transaction(redemption):
    """Maintain one read-only expense for the redemption's current IOF."""
    from ledger.models import Transaction

    item = Transaction.objects.filter(reward_redemption=redemption).first()
    if not redemption.iof_amount:
        if item:
            item.delete()
        return
    if item is None:
        item = Transaction(
            user=redemption.user,
            reward_redemption=redemption,
            category=_iof_category(redemption.user),
        )
    item.title = "IOF on reward redemption"
    item.amount = redemption.iof_amount
    item.transaction_type = Transaction.TransactionType.EXPENSE
    item.payment_channel = (
        Transaction.PaymentChannel.CREDIT_CARD
        if redemption.iof_credit_card_id
        else Transaction.PaymentChannel.ACCOUNT
    )
    item.bank_account = redemption.iof_account
    item.credit_card = redemption.iof_credit_card
    item.date = redemption.date
    item.notes = redemption.notes
    item.full_clean()
    item.save()


@transaction.atomic
def _save_reward_redemption(
    *,
    user,
    program,
    points,
    target_account,
    target_amount,
    date,
    iof_amount=ZERO,
    iof_account=None,
    iof_credit_card=None,
    notes="",
    redemption=None,
):
    original = None
    if redemption is not None:
        original = RewardRedemption.objects.select_for_update().get(pk=redemption.pk, user=user)
    # An edit restores its original points before checking the new debit.
    program = LoyaltyProgram.objects.select_for_update().get(pk=program.pk, user=user)
    available = program.balance
    if original and original.program_id == program.pk and original.loyalty_entry_id:
        available += original.points
    if available < Decimal(points):
        raise ValidationError({"points": gettext("The program does not have enough points.")})
    redemption = original or RewardRedemption(user=user)
    for field, value in {
        "program": program,
        "points": points,
        "target_account": target_account,
        "target_amount": target_amount,
        "date": date,
        "iof_amount": iof_amount,
        "iof_account": iof_account,
        "iof_credit_card": iof_credit_card,
        "notes": notes,
    }.items():
        setattr(redemption, field, value)
    redemption.full_clean()
    redemption.save()
    entry = redemption.loyalty_entry or LoyaltyEntry(user=user)
    for field, value in {
        "program": program,
        "direction": LoyaltyEntry.Direction.DEBIT,
        "kind": LoyaltyEntry.Kind.REDEMPTION,
        "amount": points,
        "date": date,
        "notes": notes,
    }.items():
        setattr(entry, field, value)
    entry.full_clean()
    entry.save()
    reward_movement, _ = BankMovement.objects.update_or_create(
        user=user,
        source_key=f"reward-redemption:{redemption.pk}:reward",
        defaults={
            "account": target_account,
            "direction": BankMovement.Direction.CREDIT,
            "kind": BankMovement.Kind.REWARD,
            "amount": target_amount,
            "effective_date": date,
            "description": notes,
        },
    )
    iof_movement = None
    old_iof_movement = redemption.iof_movement
    if iof_account is not None:
        iof_movement, _ = BankMovement.objects.update_or_create(
            user=user,
            source_key=f"reward-redemption:{redemption.pk}:iof",
            defaults={
                "account": iof_account,
                "direction": BankMovement.Direction.DEBIT,
                "kind": BankMovement.Kind.EXPENSE,
                "amount": iof_amount,
                "effective_date": date,
                "description": gettext("IOF on reward redemption: %(notes)s") % {"notes": notes},
            },
        )
    redemption.loyalty_entry = entry
    redemption.reward_movement = reward_movement
    redemption.iof_movement = iof_movement
    redemption.save(update_fields=["loyalty_entry", "reward_movement", "iof_movement"])
    if old_iof_movement and iof_movement is None:
        old_iof_movement.delete()
    sync_redemption_iof_transaction(redemption)
    return redemption


def create_reward_redemption(**kwargs):
    return _save_reward_redemption(**kwargs)


def update_reward_redemption(*, redemption, **kwargs):
    return _save_reward_redemption(redemption=redemption, **kwargs)
