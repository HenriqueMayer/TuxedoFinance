# `payments`

Full CRUD for `PaymentMethod`, plus the default-payment-method seeding signal (FR14). Structurally the twin of [`categories`](categories.md) — same view/signal shape, minus the self-relationship, plus the credit card **billing cycle** that decides which month a purchase is actually paid in.

## Files

| File | Contents |
|---|---|
| `payments/models.py` | `PaymentMethod` |
| `payments/forms.py` | `PaymentMethodForm` |
| `payments/views.py` | `PaymentMethodListView`, `PaymentMethodCreateView`, `PaymentMethodUpdateView`, `PaymentMethodDeleteView` |
| `payments/urls.py` | `app_name = 'payments'`; routes `list`, `create`, `update`, `delete` |
| `payments/signals.py` | `seed_default_payment_methods` |
| `payments/apps.py` | `PaymentsConfig.ready()` wires the signal |
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

## Default payment method seeding (FR14)

```python
DEFAULT_PAYMENT_METHODS = (
    (PaymentMethod.MethodType.CREDIT_CARD, 'Credit Card'),
    (PaymentMethod.MethodType.DEBIT_CARD, 'Debit Card'),
    (PaymentMethod.MethodType.CHECKING_ACCOUNT, 'Checking Account'),
    (PaymentMethod.MethodType.PIX, 'PIX'),
)

@receiver(post_save, sender=settings.AUTH_USER_MODEL, dispatch_uid='payments_seed_defaults')
def seed_default_payment_methods(sender, instance, created, **kwargs):
    if not created:
        return
    PaymentMethod.objects.bulk_create(
        PaymentMethod(user=instance, name=name, method_type=method_type)
        for method_type, name in DEFAULT_PAYMENT_METHODS
    )
```

One payment method **per `MethodType`** (4 total), each named after its own type by default (e.g. `name='PIX', method_type='PIX'`) — the user can rename any of them afterward (e.g. "PIX" → "Personal PIX"), since `name` and `method_type` are independent fields. Wired the same way as `categories`' signal, via `PaymentsConfig.ready()`.

**Why this exists:** identical rationale to categories — `Transaction.payment_method` is a required FK, so a brand-new user needs at least one to exist before they can record their first transaction.

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
