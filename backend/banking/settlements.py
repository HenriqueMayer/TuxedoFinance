"""Invoice settlement: the state of an invoice and its confirmed payments.

The state of an invoice (status, ``paid_at`` and the outstanding amounts) is
calculated as of a date, so it changes when the date changes. Pages calculate
it when they are read, with ``invoice_state`` or ``attach_invoice_states``.
The ``status`` and ``paid_at`` columns of ``CardInvoice`` are a cache of the
state as of the last synchronization (docs/apps/banking.md#invoice-state).
"""

from dataclasses import dataclass
from datetime import UTC, datetime, time
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum, prefetch_related_objects
from django.utils.translation import gettext as _

from banking.models import BankMovement, CardInvoice, CardInvoiceCredit, InvoicePayment
from config import clock

ZERO = Decimal("0.00")


def is_manual_invoice(invoice):
    """Return whether confirmed payments settle the invoice (manual mode).

    Manual mode is sticky for an invoice: a stored manual invoice stays
    manual, so its confirmed evidence is kept. Otherwise the card's
    ``manual_settlement_from`` decides by the due date. The call reads
    ``invoice.card``; select it with the invoice to avoid a query.
    """
    return invoice.manual_settlement or bool(
        invoice.card.manual_settlement_from
        and invoice.due_date >= invoice.card.manual_settlement_from
    )


def statement_amount_at(invoice, as_of, future_credits=None):
    """Return the statement amount that settles the invoice as of ``as_of``.

    A credit dated after ``as_of`` is a forecast, not evidence of settlement
    on that date, so it is not subtracted. ``future_credits`` is a preloaded
    set of ``(card_id, reference_month)`` keys of the owner's credits dated
    after ``as_of``. When the key of the invoice is not in it, the result is
    ``invoice.amount`` without a query. With ``None``, one query checks for
    such a credit. When one exists, the gross statement minus the credits up
    to ``as_of`` is calculated (three queries).
    """
    if future_credits is not None:
        has_future_credit = (invoice.card_id, invoice.reference_month) in future_credits
    elif invoice.card_id is None:
        # An unsaved invoice without a card has no credits.
        has_future_credit = False
    else:
        has_future_credit = CardInvoiceCredit.objects.filter(
            user_id=invoice.user_id,
            card_id=invoice.card_id,
            reference_month=invoice.reference_month,
            date__gt=as_of,
        ).exists()
    if not has_future_credit:
        return invoice.amount
    from banking.credits import invoice_credit_totals

    return max(
        ZERO,
        invoice.gross_amount
        - invoice_credit_totals(
            invoice.user,
            card_id=invoice.card_id,
            reference_month=invoice.reference_month,
            as_of=as_of,
        ),
    )


def invoice_projection(invoice, through_date, *, statement_amount=None):
    """Return the settlement values of an invoice as of ``through_date``.

    Synchronization stores ``status``, ``paid_at`` and ``manual_settlement``
    from this result; ``invoice_state`` reads the same result for pages.
    ``statement_amount`` is used only for a manual invoice; without it, the
    amount comes from ``statement_amount_at``.
    """
    if not is_manual_invoice(invoice):
        # The stored paid_at of an automatic invoice is kept as it is.
        return {
            "status": CardInvoice.Status.PAID
            if invoice.due_date <= through_date
            else CardInvoice.Status.SCHEDULED,
            "paid_at": invoice.paid_at,
            "manual_settlement": False,
            "movement_amount": invoice.amount,
        }
    if statement_amount is None:
        # Payment edits may refresh outside the source reconciliation loop.
        # A future credit is a forecast, not evidence of settlement today.
        statement_amount = statement_amount_at(invoice, through_date)
    payments = (
        [payment for payment in invoice.payments.all() if payment.date <= through_date]
        if invoice.pk
        else []
    )
    paid = sum((payment.amount for payment in payments), ZERO)
    if statement_amount <= paid and (payments or statement_amount == ZERO):
        status = CardInvoice.Status.PAID
    elif paid > ZERO:
        status = CardInvoice.Status.PARTIAL
    elif invoice.due_date < through_date:
        status = CardInvoice.Status.OVERDUE
    else:
        status = CardInvoice.Status.SCHEDULED
    # paid_at is midnight UTC of the last payment date, as earlier versions
    # stored it with TIME_ZONE = 'UTC'. The financial time zone does not
    # change it, so an upgrade does not rewrite paid invoices. The payment
    # dates are the financial record; do not show paid_at as a local time.
    paid_at = (
        datetime.combine(max(payment.date for payment in payments), time.min, tzinfo=UTC)
        if status == CardInvoice.Status.PAID and payments
        else None
    )
    return {
        "status": status,
        "paid_at": paid_at,
        "manual_settlement": True,
        "movement_amount": None,
    }


@dataclass(frozen=True)
class InvoiceState:
    """The settlement state of one invoice as of one date (``invoice_state``).

    ``status`` is a ``CardInvoice.Status`` value. For a manual invoice, the
    amounts compare ``CardInvoice.amount`` with the payments dated up to the
    date; an automatic invoice has no confirmed amount, and nothing remains
    after its due date.
    """

    status: str
    paid_at: datetime | None
    manual_settlement: bool
    confirmed_amount: Decimal
    remaining_amount: Decimal
    overpaid_amount: Decimal
    is_overdue: bool


def invoice_state(invoice, as_of, *, future_credits=None):
    """Return the ``InvoiceState`` of an invoice as of ``as_of``.

    The status comes from ``invoice_projection``. Only a manual invoice needs
    its statement amount (``statement_amount_at`` with ``future_credits``) and
    its payments; prefetch ``payments`` to avoid a query.
    """
    manual = is_manual_invoice(invoice)
    statement = statement_amount_at(invoice, as_of, future_credits) if manual else None
    projected = invoice_projection(invoice, as_of, statement_amount=statement)
    status = projected["status"]
    if manual:
        # An unsaved invoice has no payments.
        payments = invoice.payments.all() if invoice.pk else []
        confirmed = sum((payment.amount for payment in payments if payment.date <= as_of), ZERO)
        remaining = max(ZERO, invoice.amount - confirmed)
        overpaid = max(ZERO, confirmed - invoice.amount)
    else:
        confirmed = overpaid = ZERO
        remaining = ZERO if status == CardInvoice.Status.PAID else invoice.amount
    return InvoiceState(
        status=status,
        paid_at=projected["paid_at"],
        manual_settlement=manual,
        confirmed_amount=confirmed,
        remaining_amount=remaining,
        overpaid_amount=overpaid,
        is_overdue=status != CardInvoice.Status.PAID and invoice.due_date < as_of,
    )


def future_credit_keys(user_id, invoices, as_of):
    """Return the ``future_credits`` keys of ``invoice_state`` for ``invoices``.

    The keys are the ``(card_id, reference_month)`` pairs of the credits of
    ``user_id`` dated after ``as_of`` on the cards of the manual invoices
    (one query). Without a manual invoice, no query runs. Pass the owner of
    the invoices as ``user_id``.
    """
    cards = {invoice.card_id for invoice in invoices if is_manual_invoice(invoice)}
    if not cards:
        return frozenset()
    return frozenset(
        CardInvoiceCredit.objects.filter(
            user_id=user_id,
            card_id__in=cards,
            date__gt=as_of,
        ).values_list("card_id", "reference_month")
    )


def attach_invoice_states(invoices, as_of=None):
    """Calculate the state of each invoice and keep it on the instance; return the list.

    ``CardInvoice.current_state`` then uses the kept state while its date is
    today. All invoices must have one owner. The call loads the payments of
    the manual invoices when they are not prefetched (one query) and the
    owner's credits dated after ``as_of`` (``future_credit_keys``, one
    query). An invoice with such a credit calculates its gross statement
    (``statement_amount_at``). Select ``card`` with the invoices to avoid a
    query for each one.
    """
    invoices = list(invoices)
    if not invoices:
        return invoices
    as_of = as_of or clock.today()
    owners = {invoice.user_id for invoice in invoices}
    if len(owners) != 1:
        raise ValueError("attach_invoice_states() needs the invoices of one owner.")
    manual = [invoice for invoice in invoices if is_manual_invoice(invoice)]
    unloaded = [
        invoice
        for invoice in manual
        if "payments" not in getattr(invoice, "_prefetched_objects_cache", {})
    ]
    if unloaded:
        prefetch_related_objects(unloaded, "payments")
    future_credits = future_credit_keys(owners.pop(), manual, as_of)
    for invoice in invoices:
        invoice._attached_settlement_state = (
            as_of,
            invoice_state(invoice, as_of, future_credits=future_credits),
        )
    return invoices


def manual_invoice_obligations(user, as_of):
    """Outstanding obligations as of a cutoff, without inventing cash debits."""
    invoices = (
        CardInvoice.objects.filter(user=user, manual_settlement=True)
        .select_related("card__account__bank")
        .prefetch_related("payments")
    )
    rows = []
    for invoice in invoices:
        paid = sum(
            (payment.amount for payment in invoice.payments.all() if payment.date <= as_of), ZERO
        )
        # Today's net statement may include credits posted after this read's
        # cutoff. Historical obligations only use credits already posted.
        invoice.remaining_amount_at_cutoff = max(ZERO, statement_amount_at(invoice, as_of) - paid)
        # A temporary attribute avoids confusing current remaining_amount with
        # a historical or forecast cutoff selected by the caller.
        if invoice.remaining_amount_at_cutoff:
            rows.append(invoice)
    return rows


@transaction.atomic
def save_invoice_payment(payment):
    invoice = (
        CardInvoice.objects.select_for_update()
        .select_related("card__account")
        .get(pk=payment.invoice_id, user_id=payment.user_id)
    )
    payment.invoice = invoice
    if not payment.pk:
        previous = InvoicePayment.objects.filter(
            user_id=payment.user_id, confirmation_key=payment.confirmation_key
        ).first()
        if previous:
            if any(
                getattr(previous, field) != getattr(payment, field)
                for field in ("invoice_id", "account_id", "amount", "date", "notes")
            ):
                raise ValidationError(
                    _(
                        "This confirmation was already used. Reload the invoice before submitting another payment."
                    )
                )
            return previous
    payment.full_clean()
    others = invoice.payments.exclude(pk=payment.pk).aggregate(total=Sum("amount"))["total"] or ZERO
    if others + payment.amount > statement_amount_at(invoice, clock.today()):
        raise ValidationError({"amount": _("Payments cannot exceed the current invoice amount.")})
    payment.save()
    key = f"invoice-payment:{payment.pk}"
    movement, _created = BankMovement.objects.update_or_create(
        user=payment.user,
        source_key=key,
        defaults={
            "account": payment.account,
            "direction": BankMovement.Direction.DEBIT,
            "kind": BankMovement.Kind.INVOICE,
            "amount": payment.amount,
            "effective_date": payment.date,
            "description": _("%(card)s confirmed invoice payment") % {"card": invoice.card.name},
        },
    )
    payment.movement = movement
    payment.save(update_fields=["movement", "updated_at"])
    _refresh(invoice)
    return payment


def _refresh(invoice):
    # Keep the stored cache of the state current after a payment change.
    projected = invoice_projection(invoice, clock.today())
    for field in ("status", "paid_at", "manual_settlement"):
        setattr(invoice, field, projected[field])
    invoice.save(update_fields=["status", "paid_at", "manual_settlement", "updated_at"])


@transaction.atomic
def delete_invoice_payment(payment):
    invoice = CardInvoice.objects.select_for_update().get(
        pk=payment.invoice_id, user_id=payment.user_id
    )
    movement_id = payment.movement_id
    payment.delete()
    if movement_id:
        BankMovement.objects.filter(pk=movement_id, user_id=invoice.user_id).delete()
    _refresh(invoice)
