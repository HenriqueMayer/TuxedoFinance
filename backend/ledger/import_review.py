"""What the owner sees while reviewing a staged statement, and the first decisions.

``ledger.statement_import`` holds the rules: staging, the validation of a
decision, the confirmation and the undo. This module adds the reads of the
API and two helpers that save typing:

- ``guess_mapping`` proposes the columns of a CSV file from its header names
  and its first rows. The owner confirms or changes them.
- ``apply_suggestions`` gives a first decision to each row that has none. A
  row with a bank identifier that was confirmed before is skipped. A row that
  equals one recorded movement (account, date, direction and amount) is
  matched to it. A row whose description was recorded before is created with
  the category of that entry. Any other row waits for the owner.

A suggestion is a saved decision like any other: the owner sees it and can
change it before the confirmation. Nothing here creates a financial record.
"""

from datetime import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError

from banking.models import CardInvoice
from banking.settlements import attach_invoice_states
from config import clock
from ledger.models import Transaction
from ledger.statement_import import (
    decision_digest,
    row_suggestions,
    save_review,
    validate_decision,
)
from ledger.statement_parsers import inspect_csv

ZERO = Decimal("0.00")
SAMPLE_ROWS = 3
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d")
# Header names that statements of banks use, without letter case and accents.
COLUMN_NAMES = {
    "date_column": ("date", "data", "dt", "posted", "data lancamento", "data do lancamento"),
    "description_column": (
        "description",
        "descricao",
        "historico",
        "text",
        "memo",
        "title",
        "titulo",
        "estabelecimento",
        "lancamento",
        "detalhes",
    ),
    "amount_column": ("amount", "valor", "value", "montante", "quantia"),
    "debit_column": ("debit", "debito", "saida", "saidas"),
    "credit_column": ("credit", "credito", "entrada", "entradas"),
    "id_column": ("id", "identificador", "identifier", "fitid", "transaction id"),
}
EMPTY_MAPPING = {
    "date_column": "",
    "description_column": "",
    "amount_column": "",
    "debit_column": "",
    "credit_column": "",
    "id_column": "",
    "currency_column": "",
    "date_format": "%Y-%m-%d",
    "decimal_mark": ".",
}
_ACCENTS = str.maketrans("áàâãéêíóôõúç", "aaaaeeiooouc")


def _plain(text):
    return text.strip().casefold().translate(_ACCENTS)


def _rows(batch):
    return inspect_csv(batch.raw_text.encode(batch.encoding), batch.encoding)["rows"]


def guess_mapping(batch):
    """Return a column mapping for a CSV batch. A column that was not found is empty."""
    mapping = dict(EMPTY_MAPPING)
    by_name = {_plain(header): header for header in batch.headers}
    for field, names in COLUMN_NAMES.items():
        mapping[field] = next((by_name[name] for name in names if name in by_name), "")
    if mapping["amount_column"]:
        mapping["debit_column"] = mapping["credit_column"] = ""
    rows = _rows(batch)[:20]
    if mapping["date_column"]:
        values = [row[mapping["date_column"]].strip() for row in rows]
        for date_format in DATE_FORMATS:
            try:
                for value in values:
                    datetime.strptime(value, date_format)
            except ValueError:
                continue
            mapping["date_format"] = date_format
            break
    amounts = [
        row[column].strip()
        for column in (mapping["amount_column"], mapping["debit_column"], mapping["credit_column"])
        if column
        for row in rows
    ]
    # "1.234,56" and "12,5" use a decimal comma; "1,234.56" and "12.5" a point.
    if any(value.rfind(",") > value.rfind(".") for value in amounts):
        mapping["decimal_mark"] = ","
    return mapping


def _remembered_category(user, row):
    """Return the category of the latest entry recorded with the description of ``row``."""
    kind = "INCOME" if row.amount > ZERO else "EXPENSE"
    latest = (
        Transaction.objects.filter(
            user=user, title__iexact=row.description[:150], transaction_type=kind
        )
        .select_related("category")
        .order_by("-created_at", "-pk")
        .first()
    )
    if latest is None or latest.category_id is None:
        return None
    if latest.category.transaction_type not in (None, kind):
        return None
    return latest.category_id


def _empty_decision(action):
    return {
        "action": action,
        "category_id": None,
        "matched_movement_id": None,
        "invoice_id": None,
        "counterparty_account_id": None,
        "counterparty_amount": None,
    }


def apply_suggestions(user, batch):
    """Save a first decision for each row of ``batch`` that has none and a clear answer."""
    decisions, skips, taken = {}, [], set()
    for row in batch.rows.filter(action=""):
        row.batch = batch
        suggestions = row_suggestions(row)
        free = [
            movement
            for movement in suggestions["matches"]
            if movement.pk not in taken and not movement.statement_matches.exists()
        ]
        if suggestions["strong_duplicate"]:
            decision = _empty_decision("SKIP")
            skips.append(row.pk)
        elif len(free) == 1:
            decision = {**_empty_decision("MATCH"), "matched_movement_id": free[0].pk}
            taken.add(free[0].pk)
        else:
            category_id = _remembered_category(user, row)
            if category_id is None or suggestions["matches"]:
                continue
            decision = {**_empty_decision("CREATE"), "category_id": category_id}
        for field, value in decision.items():
            setattr(row, field, value)
        try:
            validate_decision(row)
        except ValidationError:
            continue  # The owner decides this row and sees the reason then.
        decisions[row.pk] = decision
    if decisions:
        save_review(user, batch.pk, decisions, partial=True, confirmed_skips=skips)


def _payable_invoices(user, today):
    """Return the invoices that a statement row can pay: confirmed mode, with an amount open."""
    invoices = attach_invoice_states(
        CardInvoice.objects.filter(user=user, amount__gt=0)
        .select_related("card__account")
        .prefetch_related("payments")
        .order_by("due_date", "pk"),
        as_of=today,
    )
    return [
        {
            "id": invoice.pk,
            "card_name": invoice.card.name,
            "month": invoice.reference_month,
            "remaining": invoice.current_state.remaining_amount,
        }
        for invoice in invoices
        if invoice.current_state.manual_settlement and invoice.current_state.remaining_amount > ZERO
    ]


def brief(batch):
    return {
        "id": batch.pk,
        "account_name": f"{batch.account.bank.name} · {batch.account.name}",
        "file_name": batch.file_name,
        "status": batch.status,
        "created_at": batch.created_at,
        "rows": batch.rows.count(),
    }


def detail(batch):
    """Return a batch with its rows, what each row can match, and what is left to decide."""
    staged = batch.status == "STAGED"
    ready = batch.status == "READY"
    account = batch.account
    rows = []
    for row in batch.rows.all():
        row.batch = batch
        suggestions = row_suggestions(row) if ready else None
        rows.append(
            {
                "id": row.pk,
                "number": row.number,
                "date": row.date,
                "amount": row.amount,
                "description": row.description,
                "action": row.action,
                "category_id": row.category_id,
                "matched_movement_id": row.matched_movement_id,
                "invoice_id": row.invoice_id,
                "counterparty_account_id": row.counterparty_account_id,
                "counterparty_amount": row.counterparty_amount,
                "duplicate": bool(suggestions and suggestions["strong_duplicate"]),
                "matches": [
                    {"id": movement.pk, "label": movement.label}
                    for movement in (suggestions["matches"] if suggestions else ())
                ],
            }
        )
    return {
        **brief(batch),
        "rows": rows,
        "account_id": account.pk,
        "currency": account.currency,
        "file_format": batch.file_format,
        "headers": batch.headers,
        "mapping": batch.mapping or (guess_mapping(batch) if staged else None),
        "sample": _rows(batch)[:SAMPLE_ROWS] if staged else [],
        "undecided": sum(1 for row in rows if not row["action"]),
        "digest": decision_digest(batch) if ready else "",
        # Confirmation needs a dated opening balance: no date is inferred.
        "needs_opening_date": bool(account.opening_balance and account.opening_date is None),
        "invoices": _payable_invoices(batch.user, clock.today()) if ready else [],
        "reconciliation": batch.reconciliation_at_confirmation or None,
    }
