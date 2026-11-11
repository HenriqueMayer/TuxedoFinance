"""Build ledger targets without saving sources, invoices or movements.

The synchronizer applies these targets atomically; read-only scenarios consume
the same schedule and settlement rules. Callers supply owned, related sources
and prefetch existing invoice payments. No input object is changed.

The occurrences and the gross statement totals come from the occurrence
engine (``transactions.schedule``) in the synchronization window of the
horizon. Card-funded points purchases are engine sources too, so all gross
statement totals come from ``schedule.statement_totals``. Invoice credits are
not occurrences: this module subtracts them from the gross totals.

An ``EXPECTED`` occurrence (R4: a month that waits for its confirmation)
never becomes a movement, whatever its date. The plan returns it in
``expected_occurrences`` instead; synchronization ignores that dictionary,
and read-only scenarios show it as expected cash. The callers attach the R4
rows of the sources first (``transactions.models.attach_schedule_rows``).
"""

from collections import defaultdict
from copy import copy
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from banking.models import BankMovement, CardInvoice
from banking.settlements import invoice_projection
from ledger import schedule
from ledger.models import Transaction
from ledger.projection import validate_occurrences

ZERO = Decimal("0.00")


def loyalty_purchase_source(entry, currency=""):
    """Return the engine source of a points purchase that a credit card paid.

    The source has one occurrence: the cash amount in the automatic statement
    month of the funding card. ``currency`` is the currency of the card
    account. Synchronization loads the card without its account and does not
    need the currency, so the default is an empty text.
    """
    card = entry.funding_credit_card
    # A points purchase is an outflow; reports count it as a bank cost.
    return schedule.ScheduleSource(
        schedule.LOYALTY_PURCHASE,
        entry.pk,
        entry.date,
        entry.cash_amount,
        currency,
        Transaction.TransactionType.EXPENSE.value,
        schedule.instrument(
            schedule.CREDIT_CARD, card.pk, card.account_id, card.closing_day, card.due_day
        ),
    )


def _too_many_targets():
    return ValidationError(
        _("This plan has too many cash events. Reduce its accounts or duration.")
    )


def build_projection_plan(
    transactions,
    loyalty_purchases,
    invoice_credits,
    existing_invoices,
    through_date,
    horizon,
    *,
    max_targets=None,
):
    transactions = list(transactions)
    loyalty_purchases = list(loyalty_purchases)
    invoice_credits = list(invoice_credits)
    existing_invoices = list(existing_invoices)
    window = schedule.Window.through(horizon)
    movements = {}
    expected = {}
    credit_transactions = []
    card_sources = []
    for item in transactions:
        validate_occurrences(item, horizon)
        if item.is_credit_card:
            credit_transactions.append(item)
            card_sources.append(item.schedule_source())
            continue
        if item.reward_redemption_id:
            continue
        income = item.transaction_type == Transaction.TransactionType.INCOME
        for occurrence in schedule.expand((item.schedule_source(),), window):
            if occurrence.status == schedule.EXPECTED:
                expected[occurrence.key] = {
                    "account_id": occurrence.instrument.account_id,
                    "direction": BankMovement.Direction.CREDIT
                    if income
                    else BankMovement.Direction.DEBIT,
                    "kind": BankMovement.Kind.INCOME if income else BankMovement.Kind.EXPENSE,
                    "amount": occurrence.amount,
                    "cash_date": occurrence.cash_date,
                    "description": item.title,
                    "transaction_id": item.id,
                }
                if max_targets is not None and len(movements) + len(expected) > max_targets:
                    raise _too_many_targets()
                continue
            movements[occurrence.key] = {
                "account_id": occurrence.instrument.account_id,
                "direction": BankMovement.Direction.CREDIT
                if income
                else BankMovement.Direction.DEBIT,
                "kind": BankMovement.Kind.INCOME if income else BankMovement.Kind.EXPENSE,
                "amount": occurrence.amount,
                "effective_date": occurrence.cash_date,
                "description": item.title,
                "invoice_id": None,
                "transfer_id": None,
            }
            if max_targets is not None and len(movements) + len(expected) > max_targets:
                raise _too_many_targets()

    loyalty_sources = [loyalty_purchase_source(entry) for entry in loyalty_purchases]
    credits_by_key = {}
    credit_sources = defaultdict(list)
    sources_by_card = defaultdict(list)
    for source in [*card_sources, *loyalty_sources]:
        sources_by_card[source.instrument.instrument_id].append(source)
    for credit in invoice_credits:
        key = (credit.card_id, credit.reference_month)
        credits_by_key[key] = credits_by_key.get(key, ZERO) + credit.amount
        credit_sources[key].append(credit)
    computed = {}
    # The limit counts card statements after each source. The count only
    # grows, so this gives the same result as a check after each occurrence.
    # Points purchases and invoice credits are not counted, as before.
    for source in card_sources:
        schedule.statement_totals(schedule.expand((source,), window), computed)
        if max_targets is not None and len(movements) + len(expected) + len(computed) > max_targets:
            raise _too_many_targets()
    schedule.statement_totals(schedule.expand(loyalty_sources, window), computed)
    for key in credits_by_key:
        if key[1] <= horizon:
            computed.setdefault(key, ZERO)
    cards = {item.credit_card_id: item.credit_card for item in credit_transactions}
    cards.update(
        {item.funding_credit_card_id: item.funding_credit_card for item in loyalty_purchases}
    )
    cards.update({credit.card_id: credit.card for credit in invoice_credits})
    cards.update({invoice.card_id: invoice.card for invoice in existing_invoices})
    existing_by_key = {
        (invoice.card_id, invoice.reference_month): invoice for invoice in existing_invoices
    }
    for key, invoice in existing_by_key.items():
        if key in computed or not invoice.payments.all():
            continue
        # A statement with confirmed payments stays, also outside the horizon.
        # Its gross total comes from the same sources, for its month only.
        card_id, reference = key
        sources = sources_by_card[card_id]
        if reference.day != 1:
            # CardInvoice.clean requires the first day of a month; a legacy
            # stored invoice can have another day. The rule before the engine
            # matched transactions by month but points purchases by exact
            # date, so no points purchase counts here. This keeps the stored
            # total of such an invoice unchanged.
            sources = [
                source for source in sources if source.source_type != schedule.LOYALTY_PURCHASE
            ]
        totals = schedule.statement_totals(
            schedule.expand(sources, schedule.Window.months(reference))
        )
        computed[key] = totals.get((card_id, reference.replace(day=1)), ZERO)
    invoices = {}
    for key, gross in computed.items():
        card_id, reference = key
        card = cards[card_id]
        due = card.due_date_for(reference)
        amount = max(ZERO, gross - credits_by_key.get(key, ZERO))
        stored = existing_by_key.get(key)
        invoice = (
            copy(stored)
            if stored is not None
            else CardInvoice(user_id=card.user_id, card=card, reference_month=reference)
        )
        invoice.amount, invoice.due_date = amount, due
        credits_at_cutoff = sum(
            (credit.amount for credit in credit_sources[key] if credit.date <= through_date), ZERO
        )
        statement = max(ZERO, gross - credits_at_cutoff)
        projection = invoice_projection(invoice, through_date, statement_amount=statement)
        if not projection["manual_settlement"]:
            credits_at_due = sum(
                (credit.amount for credit in credit_sources[key] if credit.date <= due), ZERO
            )
            projection["movement_amount"] = max(ZERO, gross - credits_at_due)
        values = {
            "due_date": due,
            "amount": amount,
            **{field: projection[field] for field in ("status", "paid_at", "manual_settlement")},
        }
        movement = None
        if projection["movement_amount"] is not None and projection["movement_amount"] > ZERO:
            # No stored description: BankMovement.label shows the card and
            # month in the active language, so the row has no language.
            movement = {
                "account_id": card.account_id,
                "direction": BankMovement.Direction.DEBIT,
                "kind": BankMovement.Kind.INVOICE,
                "amount": projection["movement_amount"],
                "effective_date": due,
                "description": "",
                "transfer_id": None,
            }
        invoices[key] = {
            "card": card,
            "invoice": stored,
            "values": values,
            "movement_values": movement,
            "statement_at_cutoff": statement,
            "gross_amount": gross,
        }
    return {
        "transaction_movements": movements,
        "invoices": invoices,
        "retained_invoice_keys": set(invoices),
        "expected_occurrences": expected,
    }
