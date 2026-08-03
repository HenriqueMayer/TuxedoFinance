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
| `templates/transactions/{list,form,confirm_delete}.html` | screens |

For the `Transaction` model's fields, constraints, and the `TransactionType` enum, see [data-model.md § Transaction](../data-model.md#transaction-transactionsmodelspy). `transactions` has no `signals.py` or default-data seeding of its own — it's the *consumer* of the categories/payments defaults, not a producer.

The model also owns the **recurrence** logic that the dashboard forecast is built on — `months_from_start()`, `amount_for_month()`, and `amount_through_month()`. Those methods, not `transaction_date` alone, decide which months a transaction affects; see [data-model.md § Recurrence](../data-model.md#recurrence-when-a-transaction-hits-a-month).

Where that run of months *begins* is not this app's decision either. `months_from_start()` subtracts `billing_offset`, which asks the **payment method** whether the purchase landed on this month's bill or the next one — so a purchase made on or after a card's best purchase day comes out of the month after the one it was recorded in. See [data-model.md § Billing cycle](../data-model.md#billing-cycle-when-a-card-purchase-actually-leaves-the-account); the rule itself lives in [`payments`](payments.md). `transaction_date` remains the purchase date throughout, and `billed_month` / `payment_date` are the derived, display-only counterparts.

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

- **FK scoping**: both `category` and `payment_method` querysets are restricted to `user`'s own records — this is the form-level half of per-user isolation (the view-level half is `get_queryset()`/`form_valid()`, same as every other app). A malicious/guessed `pk` for another user's category is rejected as an invalid choice, not merely hidden from the dropdown.
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

`_clean_fixed_until()` runs **first** in `clean()`, before the installments block, which returns early when `payment_method`/`installments` are missing. Ordering it after that early return would have silently skipped the `fixed_until` checks on exactly the submissions that already had another error, so both errors report together.

The *why* behind the field is in [data-model.md § Ending a fixed transaction](../data-model.md#ending-a-fixed-transaction-without-losing-history-fr18): editing a fixed row's amount rewrites every month it covers, past included, so a change in value is two rows rather than an edit.

Both cross-field rules live in `clean()` rather than on the model because they span two fields and only govern user-submitted data — `Transaction.objects.create(...)` in a data migration or fixture is intentionally not constrained by them.

The field is rendered **unconditionally**, not shown/hidden as the payment-method `<select>` changes: this project is deliberately zero-JS, and a CSS-only (`:has()`) toggle is impossible here because a payment method's *type* is not knowable from its `<option value>` (which is a per-user primary key). The help text carries the rule visually; `clean()` is what actually enforces it.

Two subtleties in `clean_installments`:

- `required = False` + defaulting `None` → `1` keeps the box optional. Leaving it blank means "single payment", not a validation error, and every pre-existing POST payload that never sent the field still validates.
- Only `None` is defaulted, never a falsy `0`. Writing `return installments or 1` would silently rewrite a submitted `0` into a valid `1`; letting `0` fall through means the model's `MinValueValidator(1)` rejects it in `_post_clean()`, and the error surfaces on the `installments` field.

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
        transaction_type = self.request.GET.get('type')
        if transaction_type in Transaction.TransactionType.values:
            queryset = queryset.filter(transaction_type=transaction_type)
        queryset = queryset.order_by(*self.SORT_OPTIONS[self._selected_sort()])
        return self._filter_by_billed_month(queryset)

    def _filter_by_billed_month(self, queryset):
        month = self.request.GET.get('month')
        if not month:
            return queryset
        year_part, _, month_part = month.partition('-')
        if not (year_part.isdigit() and month_part.isdigit()):
            return queryset
        year, month_number = int(year_part), int(month_part)
        if not 1 <= month_number <= 12:
            return queryset
        return [txn for txn in queryset if txn.amount_for_month(year, month_number)]
```

- `select_related('category', 'payment_method')` avoids an N+1 query when each row in the template renders `transaction.category.name`/`transaction.payment_method.name` (NFR10).
- `paginate_by = 10` — Django's built-in `ListView` pagination; the template reads `page_obj`/`is_paginated`.
- **Zero-JS GET-param filtering** (PRD 8.1.5): `?q=` searches text, `?month=YYYY-MM` filters on the **billed** month (see below), `?type=INCOME|EXPENSE|INVESTMENT` filters on `transaction_type`, and `?sort=newest|oldest` picks the `transaction_date` direction. All are read straight from query params populated by a plain `<form method="get">` in the template (see below) — there is no JavaScript anywhere in this flow, including no typeahead or live search. Malformed/unknown values (a non-numeric month, a month outside 1–12, an invalid type, an unrecognized sort) are **silently ignored** rather than raising a `400` — the queryset simply falls back to unfiltered (or to `newest`) for that parameter.
- **`?sort=newest|oldest|updated`** (`SORT_OPTIONS`) reorders the list. `newest` (`-transaction_date, -created_at`) is both the default and identical to `Transaction.Meta.ordering`, so an unfiltered list looks the same as before this param existed; `oldest` reverses it. `updated` (`-updated_at`) is the odd one out — it ignores `transaction_date` entirely and puts whatever was most recently created or edited first, which is the only way to see a past-dated entry you just added, or a fixed transaction dated in the future, land at the top. It is applied via `order_by()` **before** `_filter_by_billed_month`, since that filter may fold the queryset into a plain Python list that only preserves whatever order it already had — it does not sort anything itself.
- **The month filter is the *billed* month, not `transaction_date`** — the same question the dashboard answers, so the two screens can never disagree about which month a transaction belongs to. It matches any row whose `amount_for_month(year, month)` is non-zero, which has two consequences the earlier `transaction_date__year`/`__month` filter got wrong:
  - a credit card purchase made on or after the card's best purchase day is listed under the month its **bill is paid** — 26 July on a card opening on the 24th is an August row, not a July one (see [data-model.md § Billing cycle](../data-model.md#billing-cycle-when-a-card-purchase-actually-leaves-the-account));
  - a **fixed** transaction or an open **installment plan** is listed under *every* month it charges, not only the month it was recorded in. A subscription started in July appears under August, September, and every month after — which is precisely what makes it fixed.
  - Neither rule survives translation to a SQL predicate: the billing shift compares the purchase day against the card's own `best_purchase_day`, and a fixed transaction recurs without bound. So this one filter folds in **Python** and returns a `list`, which `ListView` paginates exactly like a queryset. It is the same trade [`dashboard.services`](dashboard.md) makes for the same reason (NFR10) — still a single round-trip, over one user's rows already narrowed by the search and type filters, which is why it runs **last**.
- **Free-text search (FR17)** spans everything a row actually displays: `title`, `notes`, and the **names of the related category and payment method**, OR'd together. Searching only `title` would have been the smaller change, but "insurance" not finding the row filed under an Insurance category is exactly the kind of miss that makes a search box feel broken.
  - The search `Q(...)` is applied to a queryset **already filtered by `user`**, so widening the match can never reach another user's rows, even for a term that matches both users' data.
  - The term is `.strip()`ed, so a stray space is not a search for `' '`; an empty result after stripping means "no search", not "search for nothing".
  - The three filters compose with **AND**: `?q=salary&type=EXPENSE` finds salary-ish *expenses*, not "salary OR expenses".
  - `icontains` is a `LIKE` scan. At the row counts a personal finance app produces that is entirely adequate; if it ever stops being so, the answer is SQLite FTS, not a hand-rolled index.
- `get_context_data` also exposes `transaction_type_choices` (to populate the `<select>`) and the current `search_query`/`month`/`type` (to keep the filter form's state and pagination links in sync across page navigation, via Django's `{% querystring %}` template tag in `list.html`).

### Create / Update / Delete

Same `LoginRequiredMixin` + user-scoped-`get_queryset()` shape as every other app. `TransactionCreateView.form_valid()` stamps `form.instance.user = self.request.user`. `TransactionDeleteView` has **no** `ProtectedError` handling — unlike `CategoryDeleteView`/`PaymentMethodDeleteView`, nothing else references a `Transaction` via a protected FK, so a plain `DeleteView.form_valid()` is sufficient; it just adds a success message.

## Routes

| Path | Name | View |
|---|---|---|
| `/transactions/` | `transactions:list` | `TransactionListView` (supports `?q=`, `?month=`, `?type=`, `?sort=`) |
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

- `list.html` — the filter bar carries a `<input type="search" name="q">` alongside the month/type/sort controls, submitted by the same `Filter` button; `Clear filters` accounts for an active search term, month, type, **or a `sort` other than the `newest` default**, and the "no matching transactions" empty state accounts for the first three (a sort choice alone never empties the list, only reorders it). Each row is color-coded by `transaction_type` (emerald/rose/amber, see [frontend.md § Design tokens](../frontend.md#design-tokens-prd-91)), with a `+`/`−` sign prefix on the amount driven purely by `transaction_type == 'INCOME'` (the stored `amount` itself is always positive — the sign is presentation-only). A `Fixed` badge appears when `is_fixed` is true, and an `Nx` badge when `is_installment_plan` is true; installment rows also show a secondary `6x R$ 500.00` line beneath the total, so the headline figure is unambiguously the full amount. The row deliberately carries no "billed" badge (removed 2026-08-03): which month a credit-card purchase is subtracted on is decided by the card's billing cycle (see [data-model.md § Billing cycle](../data-model.md#billing-cycle-when-a-card-purchase-actually-leaves-the-account)) and surfaced by the dashboard and the filter bar's **`Billed month`** control, not repeated per row. That control is labelled "Billed month" rather than "Month" precisely because it no longer means `transaction_date`: a July purchase billed in August is found under August, and a fixed row under every month it charges. The month/type filter form and pagination controls live here.
- `form.html` — renders all 10 fields via `partials/form_field.html`, except `is_fixed`, which gets custom markup (a checkbox + label/help/errors) since it isn't a standard text/select input. `installments` sits directly under `payment_method` and `fixed_until` directly under the `is_fixed` toggle — each sits next to the field it depends on.
- `confirm_delete.html` — the standard confirm-delete pattern (see [frontend.md](../frontend.md)).
