# `transactions`

The core domain entity — every cash-flow record the app exists to track. Full CRUD, paginated listing with optional filters, and the `TransactionForm` that ties `Category`/`PaymentMethod` together per-user.

## Files

| File | Contents |
|---|---|
| `transactions/models.py` | `Transaction` |
| `transactions/forms.py` | `TransactionForm` |
| `transactions/views.py` | `TransactionListView`, `TransactionCreateView`, `TransactionUpdateView`, `TransactionDeleteView` |
| `transactions/urls.py` | `app_name = 'transactions'`; routes `list`, `create`, `update`, `delete` |
| `transactions/admin.py` | `TransactionAdmin` |
| `transactions/tests.py` | 85 tests — the largest suite in the project |
| `templates/transactions/{list,form,confirm_delete}.html` | screens |

For the `Transaction` model's fields, constraints, and the `TransactionType` enum, see [data-model.md § Transaction](../data-model.md#transaction-transactionsmodelspy). `transactions` has no `signals.py` or default-data seeding of its own — it's the *consumer* of the categories/payments defaults, not a producer.

The model also owns the **recurrence** logic that the dashboard forecast is built on — `months_from_start()`, `amount_for_month()`, and `amount_through_month()`. Those methods, not `transaction_date` alone, decide which months a transaction affects; see [data-model.md § Recurrence](../data-model.md#recurrence-when-a-transaction-hits-a-month).

## Form (`TransactionForm`)

```python
class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = (
            'title', 'amount', 'transaction_type', 'category',
            'payment_method', 'installments', 'transaction_date',
            'is_fixed', 'fixed_until', 'notes',
        )
        widgets = {
            'transaction_date': forms.DateInput(attrs={'type': 'date'}),
            'fixed_until': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 4}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'installments': forms.NumberInput(
                attrs={'step': '1', 'min': '1', 'max': str(Transaction.MAX_INSTALLMENTS)},
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = Category.objects.filter(user=user)
        self.fields['payment_method'].queryset = PaymentMethod.objects.filter(user=user)
        self.fields['installments'].required = False
        for name, field in self.fields.items():
            field.widget.attrs['class'] = (
                CHECKBOX_CLASSES if name == 'is_fixed' else INPUT_CLASSES
            )
```

All 10 fields in one `ModelForm` (the 8 original FR07 fields, plus `installments` and `fixed_until`). Enforcement layers worth noting:

- **FK scoping**: both `category` and `payment_method` querysets are restricted to `user`'s own records — this is the form-level half of per-user isolation (the view-level half is `get_queryset()`/`form_valid()`, same as every other app). A malicious/guessed `pk` for another user's category is rejected as an invalid choice, not merely hidden from the dropdown — see `TransactionFormTests.test_other_users_category_is_rejected_even_if_pk_is_guessed`.
- **`amount` widget** — `min="0.01"` is a client-side hint only; the real enforcement is the model's `MinValueValidator`, which `ModelForm` validation runs regardless of what the browser sends.
- **`is_fixed`** gets a distinct `CHECKBOX_CLASSES` string instead of the shared text-input `INPUT_CLASSES`, since it's rendered as a checkbox, not a text/select input (see [frontend.md](../frontend.md)).

### Installments validation

```python
def clean_installments(self):
    installments = self.cleaned_data.get('installments')
    return 1 if installments is None else installments

def clean(self):
    cleaned_data = super().clean()
    payment_method = cleaned_data.get('payment_method')
    installments = cleaned_data.get('installments')

    if payment_method is None or installments is None:
        return cleaned_data

    is_credit_card = payment_method.method_type == PaymentMethod.MethodType.CREDIT_CARD
    if installments > 1 and not is_credit_card:
        self.add_error(
            'installments',
            'Installments are only available for credit card payments. '
            f'Keep this at 1 for "{payment_method}".',
        )

    return cleaned_data
```

`clean()` also rejects `is_fixed=True` together with `installments > 1`: one repeats forever, the other stops after N months, so allowing both would make `amount_for_month` ambiguous. They are rejected rather than resolved by a silent precedence rule.

### Ending a fixed transaction (`fixed_until`)

`clean()` also enforces two rules on `fixed_until`, factored into `_clean_fixed_until()`:

1. It requires `is_fixed` — an end date on a one-off transaction is meaningless.
2. It cannot fall before the month `transaction_date` starts in. **Compared by month, not by day**: recurrence is monthly, so `2026-03-01` and `2026-03-28` mean the same thing, and rejecting an end date of the 1st for a transaction dated the 15th of the same month would be a distinction the projection does not make.

`_clean_fixed_until()` runs **first** in `clean()`, before the installments block, which returns early when `payment_method`/`installments` are missing. Ordering it after that early return would have silently skipped the `fixed_until` checks on exactly the submissions that already had another error — `test_fixed_until_survives_alongside_an_installments_error` pins both errors reporting together.

The *why* behind the field is in [data-model.md § Ending a fixed transaction](../data-model.md#ending-a-fixed-transaction-without-losing-history-fr18): editing a fixed row's amount rewrites every month it covers, past included, so a change in value is two rows rather than an edit.

Both cross-field rules live in `clean()` rather than on the model because they span two fields and only govern user-submitted data — `Transaction.objects.create(...)` in a data migration or fixture is intentionally not constrained by them.

The field is rendered **unconditionally**, not shown/hidden as the payment-method `<select>` changes: this project is deliberately zero-JS, and a CSS-only (`:has()`) toggle is impossible here because a payment method's *type* is not knowable from its `<option value>` (which is a per-user primary key). The help text carries the rule visually; `clean()` is what actually enforces it.

Two subtleties in `clean_installments`:

- `required = False` + defaulting `None` → `1` keeps the box optional. Leaving it blank means "single payment", not a validation error, and every pre-existing POST payload that never sent the field still validates.
- Only `None` is defaulted, never a falsy `0`. Writing `return installments or 1` would silently rewrite a submitted `0` into a valid `1`; letting `0` fall through means the model's `MinValueValidator(1)` rejects it in `_post_clean()`, and the error surfaces on the `installments` field. `TransactionFormTests.test_installments_below_one_are_rejected` covers exactly this.

## Views

### `TransactionListView`

```python
class TransactionListView(LoginRequiredMixin, ListView):
    paginate_by = 10

    def get_queryset(self):
        queryset = Transaction.objects.filter(user=self.request.user).select_related(
            'category', 'payment_method'
        )
        search = self.request.GET.get('q', '').strip()
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(notes__icontains=search)
                | Q(category__name__icontains=search)
                | Q(payment_method__name__icontains=search)
            )
        month = self.request.GET.get('month')
        if month:
            year_part, _, month_part = month.partition('-')
            if year_part.isdigit() and month_part.isdigit():
                queryset = queryset.filter(
                    transaction_date__year=int(year_part),
                    transaction_date__month=int(month_part),
                )
        transaction_type = self.request.GET.get('type')
        if transaction_type in Transaction.TransactionType.values:
            queryset = queryset.filter(transaction_type=transaction_type)
        return queryset
```

- `select_related('category', 'payment_method')` avoids an N+1 query when each row in the template renders `transaction.category.name`/`transaction.payment_method.name` (NFR10).
- `paginate_by = 10` — Django's built-in `ListView` pagination; the template reads `page_obj`/`is_paginated`.
- **Zero-JS GET-param filtering** (PRD 8.1.5): `?q=` searches text, `?month=YYYY-MM` filters on `transaction_date`'s year/month, and `?type=INCOME|EXPENSE|INVESTMENT` filters on `transaction_type`. All are read straight from query params populated by a plain `<form method="get">` in the template (see below) — there is no JavaScript anywhere in this flow, including no typeahead or live search. Malformed/unknown values (a non-numeric month, an invalid type) are **silently ignored** rather than raising a `400` — the queryset simply falls back to unfiltered for that parameter.
- **Free-text search (FR17)** spans everything a row actually displays: `title`, `notes`, and the **names of the related category and payment method**, OR'd together. Searching only `title` would have been the smaller change, but "insurance" not finding the row filed under an Insurance category is exactly the kind of miss that makes a search box feel broken.
  - The search `Q(...)` is applied to a queryset **already filtered by `user`**, so widening the match can never reach another user's rows — `test_search_never_reaches_another_users_transactions` pins this with a term that matches both users' data.
  - The term is `.strip()`ed, so a stray space is not a search for `' '`; an empty result after stripping means "no search", not "search for nothing".
  - The three filters compose with **AND**: `?q=salary&type=EXPENSE` finds salary-ish *expenses*, not "salary OR expenses".
  - `icontains` is a `LIKE` scan. At the row counts a personal finance app produces that is entirely adequate; if it ever stops being so, the answer is SQLite FTS, not a hand-rolled index.
- `get_context_data` also exposes `transaction_type_choices` (to populate the `<select>`) and the current `search_query`/`month`/`type` (to keep the filter form's state and pagination links in sync across page navigation, via Django's `{% querystring %}` template tag in `list.html`).

### Create / Update / Delete

Same `LoginRequiredMixin` + user-scoped-`get_queryset()` shape as every other app. `TransactionCreateView.form_valid()` stamps `form.instance.user = self.request.user`. `TransactionDeleteView` has **no** `ProtectedError` handling — unlike `CategoryDeleteView`/`PaymentMethodDeleteView`, nothing else references a `Transaction` via a protected FK, so a plain `DeleteView.form_valid()` is sufficient; it just adds a success message.

## Routes

| Path | Name | View |
|---|---|---|
| `/transactions/` | `transactions:list` | `TransactionListView` (supports `?q=`, `?month=`, `?type=`) |
| `/transactions/create/` | `transactions:create` | `TransactionCreateView` |
| `/transactions/<pk>/edit/` | `transactions:update` | `TransactionUpdateView` |
| `/transactions/<pk>/delete/` | `transactions:delete` | `TransactionDeleteView` |

## Admin

```python
list_display = (
    'title', 'transaction_type', 'amount', 'transaction_date',
    'is_fixed', 'installments', 'category', 'payment_method', 'user',
)
list_filter = (
    'user', 'transaction_type', 'is_fixed', 'installments',
    'category', 'payment_method',
)
search_fields = ('title', 'notes')
date_hierarchy = 'transaction_date'
```

The only admin in the project with `date_hierarchy` — convenient for browsing a single user's history by month/year directly in `/admin/`.

## Templates

- `list.html` — the filter bar carries a `<input type="search" name="q">` alongside the month/type controls, submitted by the same `Filter` button; `Clear filters` and the "no matching transactions" empty state both account for an active search term. Each row is color-coded by `transaction_type` (emerald/rose/amber, see [frontend.md § Design tokens](../frontend.md#design-tokens-prd-91)), with a `+`/`−` sign prefix on the amount driven purely by `transaction_type == 'INCOME'` (the stored `amount` itself is always positive — the sign is presentation-only). A `Fixed` badge appears when `is_fixed` is true, and an `Nx` badge when `is_installment_plan` is true; installment rows also show a secondary `6x R$ 500.00` line beneath the total, so the headline figure is unambiguously the full amount. The month/type filter form and pagination controls live here.
- `form.html` — renders all 10 fields via `partials/form_field.html`, except `is_fixed`, which gets custom markup (a checkbox + label/help/errors) since it isn't a standard text/select input. `installments` sits directly under `payment_method` and `fixed_until` directly under the `is_fixed` toggle — each sits next to the field it depends on.
- `confirm_delete.html` — the standard confirm-delete pattern (see [frontend.md](../frontend.md)).

## Tests (`transactions/tests.py`, 85 tests)

- **`TransactionModelTests`** — `__str__`, `is_fixed` defaults to `False`, timestamp behavior, and three tests specifically on the positive-amount rule: rejects `0`, rejects a negative amount, accepts the smallest legal value `0.01`. Plus seven on installments: defaults to `1`, `installment_amount` equals `amount` for a single payment, splits the total for a plan, rounds to two decimals (`100.00 / 3` → `33.33`), `amount` stays the full total after a round-trip through the database, and the `< 1` / `> MAX_INSTALLMENTS` bounds are both rejected by `full_clean()`.
- **`TransactionViewTests`** — auth required on all 4 routes; list/update/delete isolation across users; full CRUD round-trip; **`test_list_filtered_by_month`** and **`test_list_filtered_by_type`** exercise the GET-param filtering end-to-end. Ten search tests (FR17) cover title, notes, category and payment-method matches; case-insensitivity and partial words; the empty/whitespace-only term meaning "no filter"; AND composition with the type filter; the term surviving into the rendered form; the no-results empty state offering a way back; and **`test_search_never_reaches_another_users_transactions`**, the security-relevant one. Three installment tests cover the HTTP layer: a credit-card POST persists `installments=6` with the total intact, a non-credit-card POST with `installments=6` re-renders the form with a field error and creates nothing, and the list screen renders the `6x` / `500.00` breakdown.
- **`TransactionFormTests`** — required fields; `category`/`payment_method` querysets scoped to the requesting user; **`test_other_users_category_is_rejected_even_if_pk_is_guessed`** (a security-relevant test — confirms the FK scoping rejects, not just hides, cross-user references); amount-zero and amount-negative rejection at the form layer too (defense in depth on top of the model validator). Six `fixed_until` tests: optional by default, accepted on a fixed transaction, rejected without `is_fixed`, rejected before the starting month, accepted in the same month as the start, and reported alongside an installments error rather than swallowed by it. Nine installment tests: omitted and blank both default to `1`, credit card accepts `6`, non-credit-card rejects `6` but accepts `1`, the `0` / `MAX_INSTALLMENTS + 1` bounds are rejected, and `is_fixed` + `installments > 1` is rejected while `is_fixed` + `installments = 1` is accepted.
- **`NumberFormatTests`** — the FR19/FR20 display format end-to-end: amounts render with the configured currency's separators (derived from `settings.CURRENCY`, so the test passes under any of them), grouping applies above a thousand, sub-thousand values still use the decimal separator, and the two directions that would break silently — the edit form's `<input type="number">` keeping `value="12345.67"`, and a submitted `2500.55` saving as `2500.55` rather than `250055`.
- **`TransactionRecurrenceTests`** — the month-contribution rules the dashboard forecast is built on: `months_from_start` arithmetic (including negative offsets and year boundaries); a one-off lands only in its own month; a fixed row repeats every month from its start but never before it; installments spread one per month across a year boundary and then stop; the final installment absorbs the rounding remainder so the parts re-sum to `amount`; and `amount_through_month` accumulates correctly and always equals the running sum of `amount_for_month`. Nine more cover `fixed_until`: the recurrence stops after that month, the end month itself still pays, the comparison is by month not day, an absent end date still repeats indefinitely, year boundaries work, `amount_through_month` stops accumulating and still equals the running sum, an end date before the start pays once rather than a negative number of times, and **`test_a_raise_is_two_rows_and_history_survives`** — the 2000-to-3000 salary scenario the field exists for.
