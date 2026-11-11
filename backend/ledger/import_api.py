"""Statement import operations of the API: stage a file, review it, confirm it, undo it.

The rules are in ``ledger.statement_import``. A staged file creates no
financial record. The confirmation creates the reviewed records in one
database transaction, and the undo removes them while they are unchanged.
"""

import base64
import binascii
import datetime as dt
from decimal import Decimal
from typing import Literal

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from ninja import Router, Schema

from banking.models import BankAccount
from config.ownership import owned, owned_choice
from ledger import import_review, statement_import
from ledger.statements import ImportBatch

router = Router()

Status = Literal["STAGED", "READY", "CONFIRMED", "UNDONE"]
Action = Literal["SKIP", "CREATE", "MATCH", "PAY_INVOICE", "TRANSFER"]


class UploadIn(Schema):
    account_id: int
    file_name: str
    #: The bytes of the file in Base64. OFX or CSV, at most 2 MiB.
    content: str
    #: The balance that the statement shows on ``closing_date``, to compare after the confirmation.
    closing_balance: Decimal | None = None
    closing_date: dt.date | None = None


class Mapping(Schema):
    date_column: str
    description_column: str
    #: One signed amount column, or the two columns below.
    amount_column: str = ""
    debit_column: str = ""
    credit_column: str = ""
    id_column: str = ""
    currency_column: str = ""
    #: A ``strptime`` format, for example ``%d/%m/%Y``.
    date_format: str = "%Y-%m-%d"
    decimal_mark: Literal[".", ","] = "."


class Decision(Schema):
    row_id: int
    action: Action
    #: For CREATE.
    category_id: int | None = None
    #: For MATCH: a movement of ``matches``.
    matched_movement_id: int | None = None
    #: For PAY_INVOICE: an invoice of ``invoices``.
    invoice_id: int | None = None
    #: For TRANSFER: the other account and the amount on its side.
    counterparty_account_id: int | None = None
    counterparty_amount: Decimal | None = None


class DecisionsIn(Schema):
    decisions: list[Decision]


class ConfirmIn(Schema):
    #: The ``digest`` of the review that the owner saw.
    digest: str


class MatchOut(Schema):
    id: int
    label: str


class RowOut(Schema):
    id: int
    number: int
    date: dt.date
    #: Signed: negative leaves the account.
    amount: Decimal
    description: str
    #: Empty until the row has a decision.
    action: Action | Literal[""]
    category_id: int | None
    matched_movement_id: int | None
    invoice_id: int | None
    counterparty_account_id: int | None
    counterparty_amount: Decimal | None
    #: The bank identifier of this row was confirmed in an earlier import.
    duplicate: bool
    #: Recorded movements with the same account, date, direction and amount.
    matches: list[MatchOut]


class PayableInvoice(Schema):
    id: int
    card_name: str
    month: dt.date
    remaining: Decimal


class Reconciliation(Schema):
    date: dt.date
    #: The balance that the statement shows.
    expected: Decimal
    #: The balance of the records on that date.
    actual: Decimal
    difference: Decimal


class ImportBrief(Schema):
    id: int
    account_name: str
    file_name: str
    status: Status
    created_at: dt.datetime
    rows: int


class ImportOut(Schema):
    id: int
    account_id: int
    account_name: str
    currency: str
    file_name: str
    file_format: Literal["CSV", "OFX"]
    status: Status
    created_at: dt.datetime
    #: The column names of a CSV file.
    headers: list[str]
    #: The chosen columns, or a proposal while the batch is STAGED.
    mapping: Mapping | None
    #: The first rows of a STAGED CSV file, by column name.
    sample: list[dict[str, str]]
    rows: list[RowOut]
    undecided: int
    digest: str
    #: The account has an opening balance without a date. The confirmation needs the date.
    needs_opening_date: bool
    invoices: list[PayableInvoice]
    reconciliation: Reconciliation | None


def _batch(user, batch_id):
    return owned(ImportBatch, user, batch_id, select_related=("account__bank", "user"))


def _detail(user, batch_id):
    return import_review.detail(_batch(user, batch_id))


@router.get("", response=list[ImportBrief], summary="List the latest statement imports")
def list_imports(request):
    batches = ImportBatch.objects.filter(user=request.user).select_related("account__bank")[:20]
    return [import_review.brief(batch) for batch in batches]


@router.post("", response=ImportOut, summary="Stage a statement file for review")
def upload(request, payload: UploadIn):
    user = request.user
    account = owned_choice(BankAccount, user, payload.account_id, "account_id")
    try:
        blob = base64.b64decode(payload.content, validate=True)
    except (binascii.Error, ValueError):
        raise ValidationError({"content": _("The file could not be read.")}) from None
    try:
        blob.decode("utf-8-sig")
        encoding = "utf-8-sig"
    except UnicodeDecodeError:
        encoding = "cp1252"  # Statements of older systems.
    name = payload.file_name.strip() or "statement"
    head = blob[:2048].upper()
    is_ofx = name.lower().endswith((".ofx", ".qfx")) or b"<OFX" in head or b"OFXHEADER" in head
    batch, created = statement_import.stage_statement(
        user,
        account.pk,
        blob,
        name,
        "OFX" if is_ofx else "CSV",
        encoding,
        closing_balance=payload.closing_balance,
        closing_date=payload.closing_date,
    )
    if created and batch.status == "READY":
        import_review.apply_suggestions(user, batch)
    return _detail(user, batch.pk)


@router.get("/{batch_id}", response=ImportOut, summary="Read a statement import")
def read_import(request, batch_id: int):
    return _detail(request.user, batch_id)


@router.put("/{batch_id}/mapping", response=ImportOut, summary="Choose the columns of a CSV file")
def set_mapping(request, batch_id: int, payload: Mapping):
    batch = _batch(request.user, batch_id)
    statement_import.map_csv_batch(request.user, batch.pk, payload.dict())
    import_review.apply_suggestions(request.user, batch)
    return _detail(request.user, batch_id)


@router.put("/{batch_id}/decisions", response=ImportOut, summary="Save the decisions of rows")
def save_decisions(request, batch_id: int, payload: DecisionsIn):
    batch = _batch(request.user, batch_id)
    decisions = {
        item.row_id: {name: value for name, value in item.dict().items() if name != "row_id"}
        for item in payload.decisions
    }
    statement_import.save_review(request.user, batch.pk, decisions, partial=True)
    return _detail(request.user, batch_id)


@router.post("/{batch_id}/confirm", response=ImportOut, summary="Create the reviewed records")
def confirm(request, batch_id: int, payload: ConfirmIn):
    batch = _batch(request.user, batch_id)
    statement_import.confirm_batch(request.user, batch.pk, payload.digest)
    return _detail(request.user, batch_id)


@router.post("/{batch_id}/undo", response=ImportOut, summary="Remove the records of an import")
def undo(request, batch_id: int):
    batch = _batch(request.user, batch_id)
    statement_import.undo_batch(request.user, batch.pk)
    return _detail(request.user, batch_id)


@router.delete(
    "/{batch_id}", response={204: None}, summary="Discard an import that was not confirmed"
)
def discard(request, batch_id: int):
    batch = _batch(request.user, batch_id)
    if batch.status == "CONFIRMED":
        raise ValidationError(_("A confirmed import is undone, not discarded."))
    batch.delete()
    return 204, None
