"""Points and miles in the Wallet: programs, manual entries and redemptions for money.

The models and ``banking.services.create_reward_redemption`` hold the rules.
This module is the surface that the API uses. It covers what 2.0 shows:

- An entry that the owner types: points earned, used or expired.
- A redemption: points leave the program and an amount enters an account.

1.x also bought points with an account or a card and charged IOF on a
redemption. Those rules stay in the models and have no operation here.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _

from banking.models import LoyaltyEntry, LoyaltyProgram, RewardRedemption
from banking.services import create_reward_redemption

ZERO = Decimal("0.00")
CENTS = Decimal("0.01")
ENTRY_LIMIT = 60
# What the owner types, as (direction, kind) of the stored entry.
MANUAL = {
    "EARNED": (LoyaltyEntry.Direction.CREDIT, LoyaltyEntry.Kind.ADJUSTMENT),
    "USED": (LoyaltyEntry.Direction.DEBIT, LoyaltyEntry.Kind.ADJUSTMENT),
    "EXPIRED": (LoyaltyEntry.Direction.DEBIT, LoyaltyEntry.Kind.EXPIRATION),
}


def _balance(program):
    """Return the points of the program with two decimals, as amounts travel."""
    return program.balance.quantize(CENTS)


def _shown_kind(entry):
    if entry.kind == LoyaltyEntry.Kind.REDEMPTION:
        return "REDEEMED"
    if entry.kind == LoyaltyEntry.Kind.EXPIRATION:
        return "EXPIRED"
    return "EARNED" if entry.direction == LoyaltyEntry.Direction.CREDIT else "USED"


def overview(user):
    return [
        {
            "id": program.pk,
            "name": program.name,
            "unit_name": program.unit_name,
            "balance": _balance(program),
        }
        for program in LoyaltyProgram.objects.filter(user=user)
    ]


def detail(program):
    """Return a program with its latest entries, newest first."""
    entries = program.entries.select_related("reward_redemption__target_account").order_by(
        "-date", "-pk"
    )[:ENTRY_LIMIT]
    rows = []
    for entry in entries:
        redemption = getattr(entry, "reward_redemption", None)
        rows.append(
            {
                "id": entry.pk,
                "kind": _shown_kind(entry),
                "amount": entry.amount,
                "date": entry.date,
                "notes": entry.notes,
                "cash_amount": redemption.target_amount if redemption else None,
                "cash_currency": redemption.target_account.currency if redemption else None,
                "account_name": redemption.target_account.name if redemption else None,
                # Entries of 1.x rules (a purchase, an invoice award) are shown and stay.
                "undoable": entry.kind != LoyaltyEntry.Kind.PURCHASE and entry.invoice_id is None,
            }
        )
    return {
        "id": program.pk,
        "name": program.name,
        "unit_name": program.unit_name,
        "balance": _balance(program),
        "entries": rows,
    }


def _name(user, name, *, except_pk=None):
    name = name.strip()
    if not name:
        raise ValidationError({"name": _("Enter a name.")})
    taken = LoyaltyProgram.objects.filter(user=user, name__iexact=name).exclude(pk=except_pk)
    if taken.exists():
        raise ValidationError({"name": _("A program with this name already exists.")})
    return name


def save_program(user, *, name, unit_name, program=None):
    program = program or LoyaltyProgram(user=user)
    program.name = _name(user, name, except_pk=program.pk)
    program.unit_name = unit_name.strip() or program.unit_name
    program.full_clean()
    program.save()
    return program


def delete_program(program):
    if program.entries.exists():
        raise ValidationError(_("This program has entries. Undo them first."))
    program.delete()


def _lock(program):
    """Serialize the changes of one program, so two requests cannot spend the same points."""
    return LoyaltyProgram.objects.select_for_update().get(pk=program.pk)


@transaction.atomic
def record_entry(program, *, kind, amount, date, notes=""):
    """Record points that the owner earned, used or lost. Points cannot go below zero."""
    program = _lock(program)
    direction, stored_kind = MANUAL[kind]
    if amount <= ZERO:
        raise ValidationError({"amount": _("Enter an amount greater than zero.")})
    if direction == LoyaltyEntry.Direction.DEBIT and amount > program.balance:
        raise ValidationError({"amount": _("The program does not have enough points.")})
    entry = LoyaltyEntry(
        user=program.user,
        program=program,
        direction=direction,
        kind=stored_kind,
        amount=amount,
        date=date,
        notes=notes.strip(),
    )
    entry.full_clean()
    entry.save()
    return entry


@transaction.atomic
def redeem(program, *, points, account, amount, date, notes=""):
    """Take ``points`` from the program and add ``amount`` to ``account``."""
    return create_reward_redemption(
        user=program.user,
        program=program,
        points=points,
        target_account=account,
        target_amount=amount,
        date=date,
        notes=notes.strip() or _("Points redemption: %(program)s") % {"program": program.name},
    )


@transaction.atomic
def undo_entry(entry):
    """Remove an entry. A redemption also returns its money from the account.

    Removing points that the program no longer has is refused.
    """
    program = _lock(entry.program)
    if entry.kind == LoyaltyEntry.Kind.PURCHASE or entry.invoice_id:
        raise ValidationError(_("This entry cannot be undone here."))
    if entry.direction == LoyaltyEntry.Direction.CREDIT and entry.amount > program.balance:
        raise ValidationError(_("Later entries use these points. Undo them first."))
    redemption = RewardRedemption.objects.filter(loyalty_entry=entry).first()
    if redemption is not None:
        movements = [redemption.reward_movement, redemption.iof_movement]
        redemption.delete()
        for movement in movements:
            if movement is not None:
                movement.delete()
    entry.delete()
