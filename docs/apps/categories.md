# Categories

The app owns income/expense classification, optional subcategories, CSV exchange,
and the default-category signup signal. See the
[data model](../data-model.md#category) for fields and relationships.

## Forms and ownership

`CategoryForm` exposes `name`, optional `transaction_type`, and optional
`parent_category`. Parent choices are scoped to the requesting user and exclude
the edited category itself. Duplicate names are rejected with a field error;
the view also handles a database uniqueness conflict if concurrent submissions
pass validation. Model validation prevents incompatible transaction-type changes.

Create/update views share `CategoryFormMixin`. Its validation handling precedes
`SuccessMessageMixin` so a rejected save cannot display a success message.
All CRUD querysets are user-scoped; another user's identifier returns 404.
Deletion of a category referenced by transactions is blocked by `PROTECT` and
reported through a localized message.

## Listing and classification

The category list combines a trimmed, case-insensitive `q` name search with an
optional `level` filter (`top` or `sub`). Missing or invalid levels do not narrow
the queryset. Filtering uses ordinary GET requests and has no pagination.

A category may be classified as income or expense. Unclassified categories
remain available for either transaction type. Existing incompatible transactions
prevent a classification change; the nullable classification migration preserves
existing records.

## Default categories

The `post_save` user signal runs only when a user is created and seeds nine
top-level categories: Groceries, Food & Dining, Subscriptions, Education, Fitness,
Transportation, Pets, Hobbies & Entertainment, and Services. Names are translated
once in the signup language, then stored as user-owned text. Users may rename,
remove, or extend them; changing interface language does not rename them.

`CategoriesConfig.ready()` registers the receiver, whose stable `dispatch_uid`
prevents duplicate registration. No financial records are seeded.

## CSV import and export

Export uses UTF-8 with this header:

```csv
name,transaction_type,parent_category
Food,EXPENSE,
Restaurants,EXPENSE,Food
Salary,INCOME,
```

`transaction_type` accepts `INCOME`, `EXPENSE`, or an empty value. Parents are
identified by category name. Import validates the whole file before writing,
resolves parents independently of row order, and skips existing names without
changing saved records. The import form requires a `.csv` file.

## Routes

| Path | Route name | Purpose |
|---|---|---|
| `/categories/` | `categories:list` | List and filter |
| `/categories/create/` | `categories:create` | Create |
| `/categories/export/` | `categories:export` | Download CSV |
| `/categories/import/` | `categories:import` | Upload CSV |
| `/categories/<pk>/edit/` | `categories:update` | Update |
| `/categories/<pk>/delete/` | `categories:delete` | Confirm and delete one category |
| `/categories/delete-all/` | `categories:delete_all` | Confirm and delete the user's categories, subject to protected references |

Screens use shared fields, validation feedback, confirmation, and empty-state
partials. Admin exposes category name, parent, and owner, with owner filtering
and name search.
