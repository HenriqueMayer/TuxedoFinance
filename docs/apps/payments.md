# `payments`

Full CRUD for `PaymentMethod`, plus the credit card **billing cycle** that decides which month a purchase is actually paid in. Structurally a near-twin of [`categories`](categories.md) — same view shape, minus the self-relationship, plus the billing-cycle fields. **No default-data seeding**: `method_type` already enumerates the four payment-method options (`MethodType` choices), so seeding four rows with those exact names would just duplicate the enum under a free-form `name`. A user's real methods are named ("Nubank Credit", "Itaú Debit") and created on the payments page; the transaction form shows an inline "No payment methods yet" hint linking there when the user has none (see FR14 / [data-model.md § Default data seeding](../data-model.md#default-data-seeding-fr14)).

## Files

| File | Contents |
|---|---|
| `payments/models.py` | `PaymentMethod` |
| `payments/forms.py` | `PaymentMethodForm` |
| `payments/views.py` | `PaymentMethodListView`, `PaymentMethodCreateView`, `PaymentMethodUpdateView`, `PaymentMethodDeleteView` |
| `payments/urls.py` | `app_name = 'payments'`; routes `list`, `create`, `update`, `delete` |
| `payments/apps.py` | `PaymentsConfig` (no `ready()` override — no signals to wire) |
| `payments/admin.py` | `PaymentMethodAdmin` |
| `templates/payments/{list,form,confirm_delete}.html` | screens |

For the `PaymentMethod` model's fields, constraints, and the `MethodType` enum, see [data-model.md § PaymentMethod](../data-model.md#paymentmethod-paymentsmodelspy).

## Billing cycle

`best_purchase_day` is what lets a purchase leave the account in a later month than it was made — a card opening its statement on the 24th subtracts a 20 June purchase from June and a 25 June one from July. `due_day` is a reminder of which day of that month the bill goes out and never moves a transaction between months. `statement_offset()` is the entire rule and lives on this model; `Transaction.months_from_start` is its only consumer, so nothing else in the project has to know a statement exists.

The full rule, the worked example, and why `due_day` is deliberately inert are in [data-model.md § Billing cycle](../data-model.md#billing-cycle-when-a-card-purchase-actually-leaves-the-account). What matters *here* is that this app owns it: adding a card type or changing how a cycle is described is a change to `payments/`, not to the dashboard.

## Form (`PaymentMethodForm`)

```python
class PaymentMethodForm(forms.ModelForm):
    class Meta:
        model = PaymentMethod
        fields = ('name', 'method_type', 'best_purchase_day', 'due_day')
```

No FK scoping is needed in `__init__` (unlike `CategoryForm`'s `parent_category`) since `PaymentMethod` has no self-relationship — per-user isolation is fully handled by the owning views' `get_queryset()` and `form_valid()`. `__init__` only applies the shared `INPUT_CLASSES` styling string to each widget.

`clean_name()` enforces `unique_payment_method_per_user` itself: `user` is not in `Meta.fields`, and `Model.validate_unique()` skips any constraint touching an excluded field, so without it a duplicate reached the INSERT as an uncaught `IntegrityError` (a 500 on submit).

`clean()` enforces the one billing-cycle rule — credit cards only. It is cross-field, and enforced server-side rather than by hiding the inputs, because the project is deliberately zero-JS: the day fields are always rendered and cannot react to the `method_type` dropdown. The two days are otherwise independent: `best_purchase_day` alone is a complete cycle, and `due_day` alone is a harmless reminder. `templates/payments/form.html` groups them in their own bordered block with a heading, so they read as one optional section rather than two loose numbers.

## Views

Same shape as `categories/views.py`: `PaymentMethodListView` + a shared `PaymentMethodFormMixin` (model, form, template, success URL, user-scoped `get_queryset`) consumed by `PaymentMethodCreateView`/`PaymentMethodUpdateView`, all `LoginRequiredMixin`.

### List search and filtering

`PaymentMethodListView` accepts two optional GET parameters. Both are applied after the queryset has been restricted to `request.user` and combine with AND:

| Parameter | Behavior |
|---|---|
| `q` | Trimmed, case-insensitive partial match against `name`. |
| `type` | Exact `MethodType` value (`CREDIT_CARD`, `DEBIT_CARD`, `CHECKING_ACCOUNT`, or `PIX`). Missing or unknown values do not filter the list. |

The available method options come directly from `PaymentMethod.MethodType.choices`. The template uses a plain `<form method="get">`, restores valid active values, offers a direct **Clear filters** link, and distinguishes an empty filtered result from an account with no payment methods. No JavaScript or pagination is involved.

### Deletion

```python
class PaymentMethodDeleteView(LoginRequiredMixin, DeleteView):
    def form_valid(self, form):
        name = self.object.name
        try:
            response = super().form_valid(form)
        except ProtectedError:
            messages.error(
                self.request,
                f'"{name}" cannot be deleted because it is still '
                'used by existing transactions.',
            )
            return redirect('payments:list')
        messages.success(self.request, f'Payment method "{name}" deleted.')
        return response
```

Identical pattern to `CategoryDeleteView` — `Transaction.payment_method` also uses `on_delete=PROTECT`, so the same `ProtectedError` → friendly-message handling applies here.

## No default data seeding

`PaymentMethod` is **not** seeded on signup (see FR14 / [data-model.md § Default data seeding](../data-model.md#default-data-seeding-fr14)). `method_type` is itself an enum of the four payment-method options (`Credit Card`, `Debit Card`, `PIX`, `Checking Account`), so seeding four rows named exactly after their own type — "Credit Card (Credit Card)", "PIX (PIX)", … — was redundant with the enum and produced an unhelpful first-run dropdown. A user's real methods are named ("Nubank Credit", "Itaú Debit") and created on the payments page.

The downstream consequence is handled in [`transactions`](transactions.md): the transaction form renders an inline "No payment methods yet — add one first" hint linking to `payments:create` when the user has none, so a brand-new account does not hit a dead-end empty dropdown.

## Routes

| Path | Name | View |
|---|---|---|
| `/payments/` | `payments:list` | `PaymentMethodListView` |
| `/payments/create/` | `payments:create` | `PaymentMethodCreateView` |
| `/payments/<pk>/edit/` | `payments:update` | `PaymentMethodUpdateView` |
| `/payments/<pk>/delete/` | `payments:delete` | `PaymentMethodDeleteView` |

## Admin

```python
list_display = ('name', 'method_type', 'best_purchase_day', 'due_day', 'user', 'created_at')
list_filter = ('user', 'method_type')
search_fields = ('name',)
```

## Templates

- `list.html` — GET name/method filters followed by one row per payment method with its type, optional billing-cycle details, and Edit/Delete actions; `partials/empty_state.html` handles no matches separately from an account with no methods.
- `form.html` / `confirm_delete.html` — the standard shared card layout (see [frontend.md](../frontend.md)).
