"""Ledger operations of the API: categories and transactions.

An operation reads a schema, applies the rules of the models and services, and
returns a schema. No financial rule lives here: ``Transaction.clean`` validates
an entry, and saving it makes ``ledger.ledger_state`` synchronize the derived
account movements and card invoices after the commit.
"""

import csv
import datetime as dt
import io
from decimal import Decimal
from typing import Literal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import ProtectedError, Q
from django.http import Http404, HttpResponse
from django.utils.translation import gettext as _
from ninja import Query, Router, Schema

from banking.api import InstrumentOut
from banking.instruments import KINDS, instrument_of, resolve
from config import clock
from config.ownership import owned, owned_choice
from ledger import commitments, schedule
from ledger.categories import Category
from ledger.category_importing import import_category_rows, read_category_csv
from ledger.consultation import (
    billed_month_occurrence,
    may_bill_between,
    requested_billed_month,
)
from ledger.models import Transaction, attach_schedule_rows

router = Router()

TransactionType = Literal["INCOME", "EXPENSE"]
PAGE_SIZE = 50
SORTS = {
    "newest": ("-date", "-created_at", "-pk"),
    "oldest": ("date", "created_at", "pk"),
    "highest": ("-amount", "-date", "-pk"),
    "lowest": ("amount", "-date", "-pk"),
}


# Categories


class CategoryOut(Schema):
    id: int
    name: str
    transaction_type: TransactionType | None
    parent_id: int | None

    @staticmethod
    def resolve_parent_id(category):
        return category.parent_category_id


class CategoryIn(Schema):
    name: str
    transaction_type: TransactionType | None = None
    parent_id: int | None = None


def _apply_category(category, user, payload: CategoryIn):
    category.name = payload.name.strip()
    category.transaction_type = payload.transaction_type
    category.parent_category = (
        owned_choice(Category, user, payload.parent_id, "parent_id") if payload.parent_id else None
    )
    category.full_clean()
    category.save()
    return category


@router.get("/categories", response=list[CategoryOut], summary="List categories")
def list_categories(request):
    return Category.objects.filter(user=request.user).order_by("name")


class CategoryFile(Schema):
    #: The text of a CSV file with the header ``name,transaction_type,parent_category``.
    content: str


class CategoryImportOut(Schema):
    created: int
    #: Rows whose name the owner already has. They are not changed.
    existing: int


# These two paths come before ``/categories/{category_id}``, which would match them.
@router.get("/categories/export", summary="Export the categories as a CSV file")
def export_categories(request):
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["name", "transaction_type", "parent_category"])
    rows = Category.objects.filter(user=request.user).select_related("parent_category")
    for category in rows.order_by("name"):
        parent = category.parent_category.name if category.parent_category_id else ""
        writer.writerow([category.name, category.transaction_type or "", parent])
    # The byte order mark makes spreadsheet programs read the accents.
    response = HttpResponse("\ufeff" + output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="tuxedo-categories.csv"'
    return response


@router.post(
    "/categories/import", response=CategoryImportOut, summary="Import categories from a CSV file"
)
def import_categories(request, payload: CategoryFile):
    try:
        rows = read_category_csv(io.BytesIO(payload.content.encode("utf-8")))
        if not rows:
            raise ValueError(_("The file has no category."))
        created = import_category_rows(request.user, rows)
    except (ValueError, ValidationError, csv.Error) as error:
        message = error.messages[0] if isinstance(error, ValidationError) else str(error)
        raise ValidationError({"content": message}) from None
    return {"created": created, "existing": len(rows) - created}


@router.post("/categories", response=CategoryOut, summary="Create a category")
@transaction.atomic
def create_category(request, payload: CategoryIn):
    return _apply_category(Category(user=request.user), request.user, payload)


@router.put("/categories/{category_id}", response=CategoryOut, summary="Change a category")
@transaction.atomic
def change_category(request, category_id: int, payload: CategoryIn):
    return _apply_category(owned(Category, request.user, category_id), request.user, payload)


@router.delete("/categories/{category_id}", response={204: None}, summary="Delete a category")
@transaction.atomic
def delete_category(request, category_id: int):
    category = owned(Category, request.user, category_id)
    try:
        category.delete()
    except ProtectedError:
        raise ValidationError(
            _("This category has records. Move them to another category before you delete it.")
        ) from None
    return 204, None


# Transactions


class CategoryRef(Schema):
    id: int
    name: str


class TransactionOut(Schema):
    id: int
    title: str
    amount: Decimal
    currency: str
    transaction_type: TransactionType
    date: dt.date
    category: CategoryRef
    instrument: InstrumentOut
    installments: int
    #: True for an entry that repeats every month.
    is_fixed: bool
    #: The last month of a repeating entry, or null when it has no end.
    fixed_until: dt.date | None
    #: True when the owner confirms each month of a repeating entry.
    requires_confirmation: bool
    notes: str
    #: A record that another operation generated. It is changed at its source.
    locked: bool
    #: The recurring income that this entry is a part of, which changes it.
    recurring_income_id: int | None
    #: The amount that falls in the requested month, when the list has a month.
    month_amount: Decimal | None = None

    @staticmethod
    def resolve_title(item):
        return item.display_title

    @staticmethod
    def resolve_currency(item):
        return item.native_currency

    @staticmethod
    def resolve_instrument(item):
        return instrument_of(item)

    @staticmethod
    def resolve_locked(item):
        return item.reward_redemption_id is not None or item.recurring_income_id is not None

    @staticmethod
    def resolve_month_amount(item):
        return getattr(item, "month_amount", None)


class TransactionIn(Schema):
    transaction_type: TransactionType = "EXPENSE"
    title: str
    amount: Decimal
    date: dt.date | None = None  # Today in the financial time zone when omitted.
    category_id: int
    instrument: str
    installments: int = 1
    is_fixed: bool = False
    fixed_until: dt.date | None = None
    requires_confirmation: bool = False
    notes: str = ""


class TransactionPage(Schema):
    items: list[TransactionOut]
    count: int
    page: int
    pages: int
    income: Decimal
    expense: Decimal


class TransactionFilters(Schema):
    q: str = ""
    month: str = ""  # YYYY-MM: the billed month (statement month for a credit card).
    type: str = ""
    category: int | None = None
    instrument: str = ""
    sort: str = "newest"
    page: int = 1


class SuggestionOut(Schema):
    category_id: int | None
    instrument: str | None


def _transactions(user):
    return (
        Transaction.objects.filter(user=user)
        .select_related(
            "category",
            "bank_account__bank",
            "debit_card__account__bank",
            "credit_card__account__bank",
        )
        .with_schedule_flags()
    )


def _apply_transaction(item, user, payload: TransactionIn):
    if item.reward_redemption_id:
        raise ValidationError(_("This record is generated. Change the redemption that created it."))
    if item.recurring_income_id:
        raise ValidationError(_("This entry is a part of a recurring income. Change the income."))
    # Every error is reported in one answer, so the owner corrects the form once.
    errors = {}
    for _channel, name, _model in KINDS.values():
        setattr(item, name, None)
    try:
        channel, field, record = resolve(user, payload.instrument)
    except ValidationError as error:
        errors.update(error.message_dict)
    else:
        setattr(item, field, record)
        # An entry by PIX keeps its channel while it stays on an account.
        if not (field == "bank_account" and item.payment_channel == "PIX"):
            item.payment_channel = channel
    try:
        item.category = owned_choice(Category, user, payload.category_id, "category_id")
    except ValidationError as error:
        errors.update(error.message_dict)
    item.transaction_type = payload.transaction_type
    item.title = payload.title.strip()
    new_date = payload.date or clock.today()
    if item.pk and item.is_fixed and payload.is_fixed and _has_past_month(item):
        # The stored amount and date give every past month of a repeating
        # entry. Changing them here would rewrite those months.
        if payload.amount != item.amount:
            errors["amount"] = [
                _(
                    "This entry has past months. Change its amount from a month in the monthly schedule."
                )
            ]
        if new_date != item.date:
            errors["date"] = [_("This entry has past months. Its first date cannot change.")]
    item.amount = payload.amount
    item.date = new_date
    item.installments = payload.installments
    item.is_fixed = payload.is_fixed
    item.fixed_until = payload.fixed_until if payload.is_fixed else None
    confirm = payload.is_fixed and payload.requires_confirmation
    if confirm and not item.requires_confirmation:
        # Confirmation starts with the current month, or with the first month
        # of an entry that starts later. Earlier months stay as recorded.
        item.confirmation_start = max(item.date, clock.today()).replace(day=1)
    elif not confirm:
        item.confirmation_start = None
    item.requires_confirmation = confirm
    item.notes = payload.notes.strip()
    try:
        # A reference that is already refused is left out of the model checks.
        skipped = {"category"} if "category_id" in errors else set()
        if "instrument" in errors:
            skipped |= {"payment_channel", "bank_account", "debit_card", "credit_card"}
            item.clean_fields(exclude=skipped)
        else:
            item.full_clean(exclude=skipped)
    except ValidationError as error:
        for name, messages in _instrument_errors(error).items():
            errors.setdefault(name, []).extend(messages)
    if errors:
        raise ValidationError(errors)
    item.save()
    return item


def _has_past_month(item):
    """Return whether a saved repeating entry has a month before the current one."""
    return item.date.replace(day=1) < clock.today().replace(day=1)


def _instrument_errors(error):
    """Report errors of the channel and record fields on the one field the client has."""
    errors = dict(error.message_dict)
    for name in ("payment_channel", "bank_account", "debit_card", "credit_card"):
        if name in errors:
            errors.setdefault("instrument", []).extend(errors.pop(name))
    if "category" in errors:
        errors["category_id"] = errors.pop("category")
    if "confirmation_start" in errors:
        errors.setdefault("requires_confirmation", []).extend(errors.pop("confirmation_start"))
    return errors


@router.get("/transactions", response=TransactionPage, summary="List transactions")
def list_transactions(request, filters: Query[TransactionFilters]):
    rows = _transactions(request.user)
    search = filters.q.strip()
    if search:
        rows = rows.filter(
            Q(title__icontains=search)
            | Q(notes__icontains=search)
            | Q(category__name__icontains=search)
            | Q(bank_account__name__icontains=search)
            | Q(bank_account__bank__name__icontains=search)
            | Q(debit_card__name__icontains=search)
            | Q(credit_card__name__icontains=search)
        )
    if filters.type in ("INCOME", "EXPENSE"):
        rows = rows.filter(transaction_type=filters.type)
    if filters.category:
        rows = rows.filter(category_id=filters.category)
    kind, _separator, pk = filters.instrument.partition(":")
    if kind in KINDS and pk.isdecimal():
        rows = rows.filter(**{f"{KINDS[kind][1]}_id": int(pk)})
    rows = rows.order_by(*SORTS.get(filters.sort, SORTS["newest"]))

    month = requested_billed_month(filters.month.strip())
    if month is None:
        items = list(rows)
        for item in items:
            item.month_amount = None
    else:
        # A month selects by the billed month and shows the amount of that month:
        # one installment of a plan, the month's amount of a recurring source.
        items = []
        first = dt.date(*month, 1)
        for item in attach_schedule_rows(rows.filter(may_bill_between(first, first))):
            occurrence = billed_month_occurrence(item, *month)
            if occurrence is not None:
                item.month_amount = occurrence.amount
                items.append(item)

    totals = {"INCOME": Decimal("0"), "EXPENSE": Decimal("0")}
    for item in items:
        totals[item.transaction_type] += item.month_amount if month else item.amount
    pages = max(1, -(-len(items) // PAGE_SIZE))
    page = min(max(filters.page, 1), pages)
    return {
        "items": items[(page - 1) * PAGE_SIZE : page * PAGE_SIZE],
        "count": len(items),
        "page": page,
        "pages": pages,
        "income": totals["INCOME"],
        "expense": totals["EXPENSE"],
    }


@router.post("/transactions", response=TransactionOut, summary="Record a transaction")
@transaction.atomic
def create_transaction(request, payload: TransactionIn):
    return _apply_transaction(Transaction(user=request.user), request.user, payload)


@router.get(
    "/transactions/suggestion", response=SuggestionOut, summary="Suggest values for a title"
)
def suggest(request, title: str = ""):
    """Return the category and instrument of the latest entry with the same title.

    Without a title, return the instrument of the latest entry, so the form
    starts with the instrument that the owner used last.
    """
    rows = Transaction.objects.filter(user=request.user, reward_redemption__isnull=True)
    title = title.strip()
    latest = (
        (rows.filter(title__iexact=title) if title else rows).order_by("-created_at", "-pk").first()
    )
    if latest is None:
        return {"category_id": None, "instrument": None}
    return {
        "category_id": latest.category_id if title else None,
        "instrument": instrument_of(latest).id,
    }


@router.get("/transactions/{transaction_id}", response=TransactionOut, summary="Read a transaction")
def read_transaction(request, transaction_id: int):
    return _owned_transaction(request.user, transaction_id)


@router.put(
    "/transactions/{transaction_id}", response=TransactionOut, summary="Change a transaction"
)
@transaction.atomic
def change_transaction(request, transaction_id: int, payload: TransactionIn):
    return _apply_transaction(
        _owned_transaction(request.user, transaction_id), request.user, payload
    )


@router.delete(
    "/transactions/{transaction_id}", response={204: None}, summary="Delete a transaction"
)
@transaction.atomic
def delete_transaction(request, transaction_id: int):
    item = _owned_transaction(request.user, transaction_id)
    if item.reward_redemption_id:
        raise ValidationError(_("This record is generated. Delete the redemption that created it."))
    if item.recurring_income_id:
        raise ValidationError(_("This entry is a part of a recurring income. Change the income."))
    item.delete()
    return 204, None


def _owned_transaction(user, transaction_id):
    item = _transactions(user).filter(pk=transaction_id).first()
    if item is None:
        raise Http404
    return item


# The monthly schedule of a repeating entry


class ScheduleMonth(Schema):
    month: dt.date
    amount: Decimal
    scheduled_amount: Decimal
    status: Literal["SCHEDULED", "ADJUSTED", "EXPECTED", "CONFIRMED", "SKIPPED"]
    #: The month waits for the owner: it is expected and its date has passed.
    awaiting: bool
    cash_date: dt.date | None
    can_skip: bool
    can_confirm: bool
    can_restore: bool
    can_change_from: bool


class AmountChange(Schema):
    month: dt.date
    amount: Decimal


class ScheduleOut(Schema):
    transaction_id: int
    title: str
    currency: str
    transaction_type: TransactionType
    requires_confirmation: bool
    months: list[ScheduleMonth]
    amount_changes: list[AmountChange]
    #: The month that "change the amount from" offers first.
    default_change_month: dt.date


class AmountChangeIn(Schema):
    month: str  # YYYY-MM
    amount: Decimal


SCHEDULE_MONTHS = 12


def _commitment(user, transaction_id):
    """Return the owned repeating entry, or 404. An entry that does not repeat has no schedule."""
    item = _owned_transaction(user, transaction_id)
    if not item.is_commitment_source or item.reward_redemption_id:
        raise Http404
    return item


def _month_or_404(value):
    requested = requested_billed_month(value)
    if requested is None:
        raise Http404
    return dt.date(*requested, 1)


def _schedule_out(user, transaction_id):
    # Read again: the services change rows that the loaded instance caches.
    item = _commitment(user, transaction_id)
    today = clock.today()
    first = schedule.offset_month(today, -2)
    last = schedule.offset_month(first, SCHEDULE_MONTHS - 1)
    source = item.schedule_source()
    return {
        "transaction_id": item.pk,
        "title": item.display_title,
        "currency": item.native_currency,
        "transaction_type": item.transaction_type,
        "requires_confirmation": item.requires_confirmation,
        "months": commitments.schedule_months(item, first, last, today=today),
        "amount_changes": [
            {"month": month, "amount": amount}
            for month, amount in schedule.amount_steps(source)[1:]
        ],
        "default_change_month": commitments.default_change_month(item, today),
    }


@router.get(
    "/transactions/{transaction_id}/schedule",
    response=ScheduleOut,
    summary="Read the months of a repeating entry",
)
def read_schedule(request, transaction_id: int):
    return _schedule_out(request.user, transaction_id)


@router.post(
    "/transactions/{transaction_id}/schedule/{month}/{action}",
    response=ScheduleOut,
    summary="Confirm, skip or restore one month",
)
def change_month(
    request, transaction_id: int, month: str, action: Literal["confirm", "skip", "restore"]
):
    item = _commitment(request.user, transaction_id)
    service = {
        "confirm": commitments.confirm_occurrence,
        "skip": commitments.skip_occurrence,
        "restore": commitments.restore_occurrence,
    }[action]
    service(item, _month_or_404(month), user=request.user)
    return _schedule_out(request.user, transaction_id)


@router.post(
    "/transactions/{transaction_id}/schedule-amounts",
    response=ScheduleOut,
    summary="Change the amount from a month",
)
def change_amount(request, transaction_id: int, payload: AmountChangeIn):
    item = _commitment(request.user, transaction_id)
    requested = requested_billed_month(payload.month.strip())
    if requested is None:
        raise ValidationError({"month": _("Choose a month.")})
    commitments.change_amount_from(item, dt.date(*requested, 1), payload.amount, user=request.user)
    return _schedule_out(request.user, transaction_id)


@router.delete(
    "/transactions/{transaction_id}/schedule-amounts/{month}",
    response=ScheduleOut,
    summary="Remove an amount change",
)
def remove_amount(request, transaction_id: int, month: str):
    item = _commitment(request.user, transaction_id)
    commitments.remove_amount_change(item, _month_or_404(month), user=request.user)
    return _schedule_out(request.user, transaction_id)
