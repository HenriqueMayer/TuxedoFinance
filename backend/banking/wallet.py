"""Read models of the Wallet: what the owner has and what the owner owes.

These functions only read. Amounts come from the services that own them
(``account_balances``, ``invoice_state``); nothing is calculated again here.
"""

from banking.models import BankMovement, CardInvoice, CreditCard, DebitCard
from banking.services import account_balances
from banking.settlements import attach_invoice_states
from config import clock

MOVEMENT_LIMIT = 60


def _invoice_row(invoice):
    state = invoice.current_state
    return {
        "id": invoice.pk,
        "reference_month": invoice.reference_month,
        "due_date": invoice.due_date,
        "amount": invoice.amount,
        "remaining": state.remaining_amount,
        "status": state.status,
        "confirm_payments": state.manual_settlement,
    }


def _card_row(card, invoices):
    """A credit card with the invoice that needs attention next."""
    today = clock.today()
    # The next invoice to act on: the oldest one that is not settled. Without
    # one, the first invoice that is not yet due.
    unsettled = [row for row in invoices if row.current_state.remaining_amount > 0]
    upcoming = [row for row in invoices if row.due_date >= today]
    chosen = min(unsettled or upcoming, key=lambda row: row.due_date, default=None)
    return {
        "id": card.pk,
        "name": card.name,
        "color": card.color,
        "closing_day": card.closing_day,
        "due_day": card.due_day,
        "confirm_payments": card.manual_settlement_from is not None,
        "next_invoice": _invoice_row(chosen) if chosen else None,
    }


def overview(user):
    """Return every bank of ``user`` with its accounts, balances and cards."""
    invoices = attach_invoice_states(
        CardInvoice.objects.filter(user=user).select_related("card").prefetch_related("payments")
    )
    invoices_by_card = {}
    for invoice in invoices:
        invoices_by_card.setdefault(invoice.card_id, []).append(invoice)
    credit_by_account, debit_by_account = {}, {}
    for card in CreditCard.objects.filter(user=user).order_by("name"):
        credit_by_account.setdefault(card.account_id, []).append(
            _card_row(card, invoices_by_card.get(card.pk, []))
        )
    for card in DebitCard.objects.filter(user=user).order_by("name"):
        debit_by_account.setdefault(card.account_id, []).append({"id": card.pk, "name": card.name})

    banks, totals = {}, {}
    for row in account_balances(user):
        account = row["account"]
        bank = banks.setdefault(
            account.bank_id,
            {
                "id": account.bank_id,
                "name": account.bank.name,
                "color": account.bank.color,
                "accounts": [],
            },
        )
        bank["accounts"].append(
            {
                "id": account.pk,
                "name": account.name,
                "currency": account.currency,
                "balance": row["balance"],
                "credit_cards": credit_by_account.get(account.pk, []),
                "debit_cards": debit_by_account.get(account.pk, []),
            }
        )
        totals[account.currency] = totals.get(account.currency, 0) + row["balance"]
    return {
        "banks": sorted(banks.values(), key=lambda bank: bank["name"].casefold()),
        "totals": [{"currency": code, "balance": totals[code]} for code in sorted(totals)],
    }


def account_movements(account, today):
    """Return the latest movements of an account up to ``today``, newest first.

    A movement with a later date (a month of a repeating entry, the debit of
    a later invoice) is not in the balance yet, and it is not listed.
    """
    rows = (
        BankMovement.objects.filter(account=account, effective_date__lte=today)
        .select_related("invoice__card", "transfer")
        .order_by("-effective_date", "-created_at", "-pk")[:MOVEMENT_LIMIT]
    )
    return [
        {
            "id": row.pk,
            "date": row.effective_date,
            "label": row.label,
            "kind": row.kind,
            "direction": row.direction,
            "amount": row.amount,
            "transfer_id": row.transfer_id,
        }
        for row in rows
    ]


def card_invoices(card, today):
    """Return the invoices of a card in two lists, each with the state of its invoices.

    The first list ends at the open statement, the one that bills a purchase
    of ``today``, and has the newest month first. The second list has the
    later statements, which installments and repeating purchases already
    fill, with the next month first.
    """
    invoices = attach_invoice_states(
        CardInvoice.objects.filter(card=card)
        .select_related("card")
        .prefetch_related("payments")
        .order_by("-reference_month")
    )
    current = card.statement_month(today)
    rows = [(invoice.reference_month, _invoice_row(invoice)) for invoice in invoices]
    return (
        [row for month, row in rows if month <= current],
        [row for month, row in reversed(rows) if month > current],
    )


def invoice_detail(invoice):
    """Return an invoice with its purchases, credits and confirmed payments."""
    # Imported here: ledger imports banking models, so a module-level import is circular.
    from ledger.consultation import billed_month_occurrence
    from ledger.models import Transaction, attach_schedule_rows

    attach_invoice_states([invoice])
    month = invoice.reference_month
    sources = attach_schedule_rows(
        Transaction.objects.filter(user_id=invoice.user_id, credit_card_id=invoice.card_id)
        .select_related("category", "credit_card__account")
        .with_schedule_flags()
        .order_by("date", "pk")
    )
    lines = []
    for item in sources:
        occurrence = billed_month_occurrence(item, month.year, month.month)
        if occurrence is not None:
            lines.append(
                {
                    "transaction_id": item.pk,
                    "title": item.display_title,
                    "date": item.date,
                    "category": item.category.name,
                    "amount": occurrence.amount,
                    "installments": item.installments,
                }
            )
    state = invoice.current_state
    return {
        **_invoice_row(invoice),
        "card_id": invoice.card_id,
        "card_name": invoice.card.name,
        "account_id": invoice.card.account_id,
        "currency": invoice.card.account.currency,
        "gross_amount": invoice.gross_amount,
        "credits_amount": invoice.credits_amount,
        "confirmed_amount": state.confirmed_amount,
        "lines": lines,
        "payments": [
            {
                "id": payment.pk,
                "date": payment.date,
                "amount": payment.amount,
                "account_id": payment.account_id,
            }
            for payment in invoice.payments.all().order_by("date", "pk")
        ],
    }
