"""Payment instruments: the accounts and cards that a transaction can use.

The API names an instrument with one string, ``account:3``, ``debit:7`` or
``credit:4``, so the entry form has one choice instead of a channel and three
record fields.
"""

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from banking.models import BankAccount, CreditCard, DebitCard

KINDS = {
    "account": ("ACCOUNT", "bank_account", BankAccount),
    "debit": ("DEBIT_CARD", "debit_card", DebitCard),
    "credit": ("CREDIT_CARD", "credit_card", CreditCard),
}


@dataclass(frozen=True)
class Instrument:
    id: str
    kind: str
    name: str
    bank_name: str
    account_name: str
    currency: str
    color: str


def _from_account(account):
    return Instrument(
        id=f"account:{account.pk}",
        kind="account",
        name=account.name,
        bank_name=account.bank.name,
        account_name=account.name,
        currency=account.currency,
        color=account.bank.color,
    )


def _from_card(kind, card):
    return Instrument(
        id=f"{kind}:{card.pk}",
        kind=kind,
        name=card.name,
        bank_name=card.account.bank.name,
        account_name=card.account.name,
        currency=card.account.currency,
        color=card.color,
    )


def instruments_of(user):
    """Return every instrument of ``user``: accounts first, then debit and credit cards."""
    accounts = BankAccount.objects.filter(user=user).select_related("bank")
    result = [_from_account(account) for account in accounts.order_by("bank__name", "name")]
    for kind, model in (("debit", DebitCard), ("credit", CreditCard)):
        cards = model.objects.filter(user=user, account__user=user).select_related("account__bank")
        result += [_from_card(kind, card) for card in cards.order_by("name")]
    return result


def instrument_of(transaction):
    """Return the instrument of a saved transaction."""
    if transaction.bank_account_id:
        return _from_account(transaction.bank_account)
    if transaction.debit_card_id:
        return _from_card("debit", transaction.debit_card)
    return _from_card("credit", transaction.credit_card)


def resolve(user, value):
    """Return ``(payment channel, field name, record)`` for an instrument id.

    A malformed id, an unknown record and another owner's record give the same
    field error.
    """
    kind, _separator, pk = str(value or "").partition(":")
    if kind in KINDS and pk.isdecimal():
        channel, field, model = KINDS[kind]
        record = model.objects.filter(user=user, pk=int(pk)).first()
        if record is not None:
            return channel, field, record
    raise ValidationError({"instrument": _("Choose one of your accounts or cards.")})
