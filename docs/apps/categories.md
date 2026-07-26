# `categories`

Full CRUD for `Category`, including subcategories via a self-relationship, plus the default-category seeding signal (FR14).

## Files

| File | Contents |
|---|---|
| `categories/models.py` | `Category` |
| `categories/forms.py` | `CategoryForm` |
| `categories/views.py` | `CategoryListView`, `CategoryCreateView`, `CategoryUpdateView`, `CategoryDeleteView` |
| `categories/urls.py` | `app_name = 'categories'`; routes `list`, `create`, `update`, `delete` |
| `categories/signals.py` | `seed_default_categories` |
| `categories/apps.py` | `CategoriesConfig.ready()` wires the signal |
| `categories/admin.py` | `CategoryAdmin` |
| `categories/tests.py` | 24 tests |
| `templates/categories/{list,form,confirm_delete}.html` | screens |

For the `Category` model's fields and constraints, see [data-model.md § Category](../data-model.md#category-categoriesmodelspy).

## Form (`CategoryForm`)

```python
class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ('name', 'parent_category')

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = Category.objects.filter(user=user)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        self.fields['parent_category'].queryset = queryset
        self.fields['parent_category'].required = False
```

Two things happen in `__init__` that aren't visible from `Meta` alone:

1. **User-scoped parent choices** — the `parent_category` dropdown only ever lists the requesting user's own categories, never another user's (the view passes `user=self.request.user` via `get_form_kwargs()`).
2. **No self-parenting** — when editing an existing category, that category's own `pk` is excluded from its own parent choices, so a category can never be set as its own parent. (This guards against direct self-reference only; it does not walk the full ancestor chain — see the caveat in [data-model.md](../data-model.md#category-categoriesmodelspy).)

## Views

All four are `LoginRequiredMixin` CBVs. `CategoryListView` and the shared `CategoryFormMixin` both filter `get_queryset()` by `self.request.user` — a `404`, not another user's data, is what you get for guessing another user's category `pk`.

### Create / Update

```python
class CategoryCreateView(SuccessMessageMixin, CategoryFormMixin, CreateView):
    success_message = 'Category "%(name)s" created.'

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)
```

`CategoryUpdateView` reuses the same `CategoryFormMixin` (model, form class, template, success URL, user-scoped queryset, `get_form_kwargs`) and needs no `form_valid` override — the instance already belongs to `self.request.user` by construction of `get_queryset()`.

### Deletion

```python
class CategoryDeleteView(LoginRequiredMixin, DeleteView):
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
            return redirect('categories:list')
        messages.success(self.request, f'Category "{name}" deleted.')
        return response
```

`Transaction.category` uses `on_delete=PROTECT` (see [data-model.md § Deletion integrity](../data-model.md#deletion-integrity)), so deleting a category still referenced by any transaction raises `ProtectedError` at the database layer. This view is the one place that exception is caught and turned into a friendly, redirect-with-message UX instead of a 500 — the exact same pattern `PaymentMethodDeleteView` uses.

## Default category seeding (FR14)

```python
DEFAULT_CATEGORY_NAMES = (
    'Groceries', 'Food & Dining', 'Subscriptions', 'Education',
    'Fitness', 'Transportation', 'Pets', 'Hobbies & Entertainment', 'Services',
)

@receiver(post_save, sender=settings.AUTH_USER_MODEL, dispatch_uid='categories_seed_defaults')
def seed_default_categories(sender, instance, created, **kwargs):
    if not created:
        return
    Category.objects.bulk_create(
        Category(user=instance, name=name) for name in DEFAULT_CATEGORY_NAMES
    )
```

Fires once, on the `post_save` signal of the `User` model, only when `created=True` (never on a profile edit/re-save). Wired via:

```python
class CategoriesConfig(AppConfig):
    name = 'categories'

    def ready(self):
        import categories.signals  # noqa: F401
```

**Why this exists:** `Transaction.category` is a required FK. Without this signal, a brand-new user would hit a dead end — an empty dropdown — the first time they tried to record a transaction. All 9 default categories are top-level (no `parent_category`); the user is free to add subcategories or additional top-level categories afterward. `dispatch_uid='categories_seed_defaults'` prevents the receiver from double-registering if `categories.signals` is ever imported more than once (e.g. Django's autoreloader).

## Routes

| Path | Name | View |
|---|---|---|
| `/categories/` | `categories:list` | `CategoryListView` |
| `/categories/create/` | `categories:create` | `CategoryCreateView` |
| `/categories/<pk>/edit/` | `categories:update` | `CategoryUpdateView` |
| `/categories/<pk>/delete/` | `categories:delete` | `CategoryDeleteView` |

## Admin

```python
list_display = ('name', 'parent_category', 'user', 'created_at')
list_filter = ('user',)
search_fields = ('name',)
```

## Templates

- `list.html` — one row per category, showing "Subcategory of {parent}" or "Top-level category"; Edit/Delete actions; `partials/empty_state.html` when the user has none (shouldn't normally happen post-signup, but reachable if all categories are deleted — though `PROTECT` blocks deleting any still in use).
- `form.html` / `confirm_delete.html` — the standard shared card layout (see [frontend.md](../frontend.md)).

## Tests (`categories/tests.py`, 24 tests)

- **`CategoryModelTests`** — default seeding count/names, `__str__` (top-level vs. subcategory), `created_at` immutability, per-user uniqueness (`IntegrityError` on duplicate, allowed across different users), `ProtectedError` on delete-while-referenced.
- **`CategoryViewTests`** — auth required on all 4 routes; list only shows own categories; `404` (not another user's data) on update/delete of another user's category; full create/update/delete round-trip; the `ProtectedError` → friendly-message path end-to-end via `messages`.
- **`CategoryFormTests`** — `name` required; `parent_category` queryset scoped to the requesting user; a category cannot be set as its own parent on edit; a valid subcategory submission passes validation.
