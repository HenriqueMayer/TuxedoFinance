"""Banking operations of the API: instruments and the Wallet.

An operation reads a schema, calls the model or service that owns the rule,
and returns a schema. Balances and invoice states are read from
``banking.wallet``; they are never calculated here.
"""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Literal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import ProtectedError
from django.utils.translation import gettext as _
from ninja import Router, Schema

from accounts.models import UserPreference
from banking import wallet
from banking.instruments import instruments_of
from banking.models import (
    Bank,
    BankAccount,
    BankTransfer,
    CardInvoice,
    CreditCard,
    DebitCard,
    ExchangeRate,
    InvoicePayment,
)
from banking.services import create_transfer, delete_transfer
from banking.settlements import delete_invoice_payment, save_invoice_payment
from config import clock
from config.currencies import CURRENCIES
from config.ownership import owned, owned_choice

router = Router()

CurrencyCode = Literal[tuple(CURRENCIES)]


class InstrumentOut(Schema):
    id: str
    kind: Literal["account", "debit", "credit"]
    name: str
    bank_name: str
    account_name: str
    currency: str
    color: str


class AccountIn(Schema):
    bank_name: str
    name: str
    currency: CurrencyCode = "BRL"
    opening_balance: Decimal = Decimal("0")
    opening_date: dt.date | None = None


class CardIn(Schema):
    account: str  # An instrument id of kind "account".
    name: str


class CreditCardIn(CardIn):
    closing_day: int
    due_day: int
    #: True when the owner confirms each invoice payment. False when the
    #: invoice is settled from the account on its due date.
    confirm_payments: bool = False


@router.get("/instruments", response=list[InstrumentOut], summary="List accounts and cards")
def list_instruments(request):
    return instruments_of(request.user)


@router.post("/accounts", response=InstrumentOut, summary="Create an account")
@transaction.atomic
def create_account(request, payload: AccountIn):
    # One step for the owner: a bank with this name is reused or created.
    bank_name = payload.bank_name.strip()
    bank = Bank.objects.filter(user=request.user, name__iexact=bank_name).first()
    if bank is None:
        bank = Bank(user=request.user, name=bank_name)
        bank.full_clean()
        bank.save()
    account = BankAccount(
        user=request.user,
        bank=bank,
        name=payload.name.strip(),
        currency=payload.currency,
        opening_balance=payload.opening_balance,
        opening_date=payload.opening_date,
    )
    account.full_clean()
    account.save()
    return next(item for item in instruments_of(request.user) if item.id == f"account:{account.pk}")


def _account_of(user, instrument_id):
    kind, _separator, pk = instrument_id.partition(":")
    return owned_choice(
        BankAccount, user, pk if kind == "account" and pk.isdecimal() else None, "account"
    )


def _card_out(user, kind, card):
    return next(item for item in instruments_of(user) if item.id == f"{kind}:{card.pk}")


@router.post("/credit-cards", response=InstrumentOut, summary="Create a credit card")
@transaction.atomic
def create_credit_card(request, payload: CreditCardIn):
    card = CreditCard(
        user=request.user,
        account=_account_of(request.user, payload.account),
        name=payload.name.strip(),
        closing_day=payload.closing_day,
        due_day=payload.due_day,
        manual_settlement_from=_confirm_from(None, payload.confirm_payments),
    )
    card.full_clean()
    card.save()
    return _card_out(request.user, "credit", card)


@router.post("/debit-cards", response=InstrumentOut, summary="Create a debit card")
@transaction.atomic
def create_debit_card(request, payload: CardIn):
    card = DebitCard(
        user=request.user,
        account=_account_of(request.user, payload.account),
        name=payload.name.strip(),
    )
    card.full_clean()
    card.save()
    return _card_out(request.user, "debit", card)


def _confirm_from(current, wanted):
    """Return the first month of confirmed payments for a card setting.

    Turning the setting on starts with the current month and keeps an earlier
    start. Turning it off affects new invoices only: an invoice that already
    uses confirmed payments keeps them.
    """
    if not wanted:
        return None
    return current or clock.today().replace(day=1)


# The Wallet


class InvoiceRow(Schema):
    id: int
    reference_month: dt.date
    due_date: dt.date
    amount: Decimal
    remaining: Decimal
    status: Literal["SCHEDULED", "PARTIAL", "OVERDUE", "PAID"]
    confirm_payments: bool


class CreditCardRow(Schema):
    id: int
    name: str
    color: str
    closing_day: int
    due_day: int
    confirm_payments: bool
    next_invoice: InvoiceRow | None


class DebitCardRow(Schema):
    id: int
    name: str


class AccountRow(Schema):
    id: int
    name: str
    currency: str
    balance: Decimal
    credit_cards: list[CreditCardRow]
    debit_cards: list[DebitCardRow]


class BankRow(Schema):
    id: int
    name: str
    color: str
    accounts: list[AccountRow]


class CurrencyTotal(Schema):
    currency: str
    balance: Decimal


class WalletOut(Schema):
    banks: list[BankRow]
    totals: list[CurrencyTotal]


class MovementRow(Schema):
    id: int
    date: dt.date
    label: str
    kind: str
    direction: Literal["CREDIT", "DEBIT"]
    amount: Decimal
    transfer_id: int | None


class AccountOut(Schema):
    id: int
    bank_id: int
    bank_name: str
    name: str
    currency: str
    opening_balance: Decimal
    opening_date: dt.date | None
    balance: Decimal
    movements: list[MovementRow]


class AccountChange(Schema):
    bank_name: str
    name: str
    opening_balance: Decimal
    opening_date: dt.date | None = None


class CreditCardOut(Schema):
    id: int
    account_id: int
    name: str
    currency: str
    closing_day: int
    due_day: int
    confirm_payments: bool
    invoices: list[InvoiceRow]


class CreditCardChange(Schema):
    name: str
    closing_day: int
    due_day: int
    confirm_payments: bool


class NameChange(Schema):
    name: str


class InvoiceLine(Schema):
    transaction_id: int
    title: str
    date: dt.date
    category: str
    amount: Decimal
    installments: int


class PaymentRow(Schema):
    id: int
    date: dt.date
    amount: Decimal
    account_id: int


class InvoiceOut(InvoiceRow):
    card_id: int
    card_name: str
    account_id: int
    currency: str
    gross_amount: Decimal
    credits_amount: Decimal
    confirmed_amount: Decimal
    lines: list[InvoiceLine]
    payments: list[PaymentRow]


class PaymentIn(Schema):
    account_id: int
    amount: Decimal
    date: dt.date | None = None  # Today when omitted.
    #: A value that the client creates once for each payment form. A repeated
    #: request with the same key records one payment.
    confirmation_key: uuid.UUID


class TransferIn(Schema):
    source_account_id: int
    destination_account_id: int
    amount: Decimal
    #: What the destination receives, for accounts in different currencies.
    destination_amount: Decimal | None = None
    date: dt.date | None = None  # Today when omitted.
    notes: str = ""


def _protected(message):
    return ValidationError(message)


def _account_out(account):
    return {
        "id": account.pk,
        "bank_id": account.bank_id,
        "bank_name": account.bank.name,
        "name": account.name,
        "currency": account.currency,
        "opening_balance": account.opening_balance,
        "opening_date": account.opening_date,
        "balance": account.current_balance(),
        "movements": wallet.account_movements(account),
    }


def _card_detail(card):
    return {
        "id": card.pk,
        "account_id": card.account_id,
        "name": card.name,
        "currency": card.account.currency,
        "closing_day": card.closing_day,
        "due_day": card.due_day,
        "confirm_payments": card.manual_settlement_from is not None,
        "invoices": wallet.card_invoices(card),
    }


@router.get("/wallet", response=WalletOut, summary="Read banks, accounts, balances and cards")
def read_wallet(request):
    # The Wallet is where a new month is first noticed. Synchronizing here
    # extends the invoice horizon; it is one SELECT when nothing changed.
    from ledger.projection import ProjectionLimitExceeded
    from ledger.services import ensure_ledger_current

    try:
        ensure_ledger_current(request.user)
    except ProjectionLimitExceeded:
        pass  # The stored rows are shown; the owner corrects the source in Transactions.
    return wallet.overview(request.user)


@router.get("/accounts/{account_id}", response=AccountOut, summary="Read an account")
def read_account(request, account_id: int):
    return _account_out(owned(BankAccount, request.user, account_id, select_related=("bank",)))


@router.put("/accounts/{account_id}", response=AccountOut, summary="Change an account")
@transaction.atomic
def change_account(request, account_id: int, payload: AccountChange):
    account = owned(BankAccount, request.user, account_id, select_related=("bank",))
    bank_name = payload.bank_name.strip()
    if bank_name.casefold() != account.bank.name.casefold():
        bank = Bank.objects.filter(user=request.user, name__iexact=bank_name).first()
        if bank is None:
            bank = Bank(user=request.user, name=bank_name)
            bank.full_clean()
            bank.save()
        previous, account.bank = account.bank, bank
    else:
        previous = None
    account.name = payload.name.strip()
    account.opening_balance = payload.opening_balance
    account.opening_date = payload.opening_date
    # The currency is not changed here: amounts already recorded are in it.
    account.clean_fields()
    account.validate_constraints()
    account.save()
    if previous is not None and not previous.accounts.exists():
        previous.delete()  # A bank is only a group of accounts; an empty one is removed.
    return _account_out(account)


@router.delete("/accounts/{account_id}", response={204: None}, summary="Delete an account")
@transaction.atomic
def delete_account(request, account_id: int):
    account = owned(BankAccount, request.user, account_id, select_related=("bank",))
    bank = account.bank
    try:
        account.delete()
    except ProtectedError:
        raise _protected(
            _(
                "This account has records. Delete or move its entries and cards before you delete it."
            )
        ) from None
    if not bank.accounts.exists():
        bank.delete()
    return 204, None


@router.get("/credit-cards/{card_id}", response=CreditCardOut, summary="Read a credit card")
def read_credit_card(request, card_id: int):
    return _card_detail(owned(CreditCard, request.user, card_id, select_related=("account",)))


@router.put("/credit-cards/{card_id}", response=CreditCardOut, summary="Change a credit card")
@transaction.atomic
def change_credit_card(request, card_id: int, payload: CreditCardChange):
    card = owned(CreditCard, request.user, card_id, select_related=("account",))
    card.name = payload.name.strip()
    card.closing_day = payload.closing_day
    card.due_day = payload.due_day
    card.manual_settlement_from = _confirm_from(
        card.manual_settlement_from, payload.confirm_payments
    )
    card.full_clean()
    card.save()
    return _card_detail(card)


@router.delete("/credit-cards/{card_id}", response={204: None}, summary="Delete a credit card")
@transaction.atomic
def delete_credit_card(request, card_id: int):
    card = owned(CreditCard, request.user, card_id)
    try:
        # Invoices without purchases are derived rows; they go with the card.
        card.invoices.filter(amount=0, payments__isnull=True).delete()
        card.delete()
    except ProtectedError:
        raise _protected(
            _("This card has purchases or invoices. Delete its entries first.")
        ) from None
    return 204, None


@router.put("/debit-cards/{card_id}", response=DebitCardRow, summary="Rename a debit card")
@transaction.atomic
def change_debit_card(request, card_id: int, payload: NameChange):
    card = owned(DebitCard, request.user, card_id)
    card.name = payload.name.strip()
    card.full_clean()
    card.save()
    return card


@router.delete("/debit-cards/{card_id}", response={204: None}, summary="Delete a debit card")
@transaction.atomic
def delete_debit_card(request, card_id: int):
    card = owned(DebitCard, request.user, card_id)
    try:
        card.delete()
    except ProtectedError:
        raise _protected(_("This card has entries. Delete or move them first.")) from None
    return 204, None


def _owned_invoice(user, invoice_id):
    return owned(CardInvoice, user, invoice_id, select_related=("card__account",))


@router.get("/invoices/{invoice_id}", response=InvoiceOut, summary="Read an invoice")
def read_invoice(request, invoice_id: int):
    return wallet.invoice_detail(_owned_invoice(request.user, invoice_id))


@router.post(
    "/invoices/{invoice_id}/payments", response=InvoiceOut, summary="Confirm an invoice payment"
)
@transaction.atomic
def pay_invoice(request, invoice_id: int, payload: PaymentIn):
    invoice = _owned_invoice(request.user, invoice_id)
    save_invoice_payment(
        InvoicePayment(
            user=request.user,
            invoice=invoice,
            account=owned_choice(BankAccount, request.user, payload.account_id, "account_id"),
            amount=payload.amount,
            date=payload.date or clock.today(),
            confirmation_key=payload.confirmation_key,
        )
    )
    return wallet.invoice_detail(_owned_invoice(request.user, invoice_id))


@router.delete(
    "/invoice-payments/{payment_id}", response={204: None}, summary="Undo an invoice payment"
)
@transaction.atomic
def undo_payment(request, payment_id: int):
    delete_invoice_payment(owned(InvoicePayment, request.user, payment_id))
    return 204, None


@router.post("/transfers", response={204: None}, summary="Transfer between two accounts")
@transaction.atomic
def transfer(request, payload: TransferIn):
    source = owned_choice(BankAccount, request.user, payload.source_account_id, "source_account_id")
    destination = owned_choice(
        BankAccount, request.user, payload.destination_account_id, "destination_account_id"
    )
    received = payload.destination_amount
    if source.currency != destination.currency and received is None:
        raise ValidationError(
            {"destination_amount": _("Enter the amount that the destination account receives.")}
        )
    try:
        create_transfer(
            user=request.user,
            source_account=source,
            destination_account=destination,
            source_amount=payload.amount,
            destination_amount=payload.amount if received is None else received,
            date=payload.date or clock.today(),
            notes=payload.notes.strip(),
        )
    except ValidationError as error:
        if not hasattr(error, "error_dict"):
            raise
        # The request has account ids, and one amount unless the currencies differ.
        names = {
            "source_amount": "amount",
            "destination_amount": "amount" if received is None else "destination_amount",
            "source_account": "source_account_id",
            "destination_account": "destination_account_id",
        }
        errors = {}
        for field, messages in error.message_dict.items():
            target = errors.setdefault(names.get(field, field), [])
            target.extend(message for message in messages if message not in target)
        raise ValidationError(errors) from None
    return 204, None


@router.delete("/transfers/{transfer_id}", response={204: None}, summary="Undo a transfer")
@transaction.atomic
def undo_transfer(request, transfer_id: int):
    delete_transfer(user=request.user, transfer=owned(BankTransfer, request.user, transfer_id))
    return 204, None


# Exchange rates


class Created(Schema):
    id: int


class ExchangeRateOut(Schema):
    id: int
    #: One unit of this currency is worth ``rate`` units of ``to_currency``.
    from_currency: str
    to_currency: str
    rate: Decimal
    effective_date: dt.date


class ExchangeRateIn(Schema):
    from_currency: CurrencyCode
    #: The currency of totals when omitted.
    to_currency: CurrencyCode | None = None
    rate: Decimal
    effective_date: dt.date | None = None  # Today when omitted.


@router.get("/exchange-rates", response=list[ExchangeRateOut], summary="List the exchange rates")
def list_exchange_rates(request):
    return ExchangeRate.objects.filter(user=request.user)[:200]


@router.post("/exchange-rates", response=Created, summary="Record the exchange rate of a date")
@transaction.atomic
def record_exchange_rate(request, payload: ExchangeRateIn):
    user = request.user
    target = payload.to_currency or UserPreference.for_user(user).base_currency
    when = payload.effective_date or clock.today()
    # A pair has one rate for each date: the same date again replaces it.
    rate = ExchangeRate.objects.filter(
        user=user, from_currency=payload.from_currency, to_currency=target, effective_date=when
    ).first() or ExchangeRate(
        user=user, from_currency=payload.from_currency, to_currency=target, effective_date=when
    )
    rate.rate = payload.rate
    rate.full_clean()
    rate.save()
    return {"id": rate.pk}


@router.delete("/exchange-rates/{rate_id}", response={204: None}, summary="Delete an exchange rate")
def delete_exchange_rate(request, rate_id: int):
    owned(ExchangeRate, request.user, rate_id).delete()
    return 204, None
