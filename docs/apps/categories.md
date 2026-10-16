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
optional `level` filter (`top` or `sub`) and `type` filter (`INCOME`, `EXPENSE`
or `unclassified`). Missing or invalid filters do not narrow the queryset.
Filtering uses ordinary GET requests and has no pagination.

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

## Form keyboard behavior

Parent-category selection uses the shared searchable record picker: type to
filter, use arrows to highlight and Enter to confirm. Escape/Tab restore the
committed choice. The native select remains available without JavaScript, with
ownership and hierarchy validation on the server. Follow the
[mandatory shared form contract](../frontend.md#keyboard-and-choice-contract).

## Hierarchy and secondary actions

The list groups a top-level category with its children, shows its income/expense
classification and direct transaction count, and supports name, level and type
filters. Unclassified categories retain their existing compatibility with both
income and expenses. Add subcategory supplies an owned parent as explicit form
context. Existing category names are never changed by translation or filtering.

The compact list uses a common row grid for parents and leaves: name, type,
direct transaction count and displayed child count align in columns on desktop.
Every row reserves the same action space, and nested rows indent only their name
area. Small screens place metadata below the name and retain 44px action targets.
Zero child counts are visually omitted on small screens but remain available to
assistive technology; direct transaction counts retain their ordinary display.
Parent context remains available to assistive technology without repeating a
visual parent line for every child.

Groups start collapsed. Clicking a parent name (or activating its disclosure with
Enter/Space) hides only its descendants; its Edit, Add subcategory and secondary
actions stay available. Collapse all / Expand all affect every displayed group,
including nested ones. A fresh page load starts collapsed; browser history restores
the state of the previous page without storing a user preference.

Grouping uses user-scoped results without extra per-category queries. Filters
retain the owned ancestors of matching descendants as labelled parent context;
the result count includes matches only. Matching paths open automatically and
unrelated branches are omitted. An ancestor is context rather than another
search match. Foreign parent references are never exposed, even in legacy data.
The forest builder visits each record once, including legacy cyclic relationships.
Without JavaScript, native disclosures still reveal every category and its
actions; global enhancement controls stay hidden. Parent actions are siblings
of the disclosure, so collapsing descendants does not hide the parent's Edit
or secondary menu. Filtering and editing work through native navigation.

Import, export and Delete all are secondary options. Default CSV export preserves
the import contract. `?format=spreadsheet` selects the separately named spreadsheet
variant, which neutralizes formula-like text and is not intended for faithful
reimport. Imports do not strip prefixes from names automatically.

Category creation/editing can carry a validated local `next` origin. Save/Cancel
retain the list's search/type/level filters and invalid responses keep the same
origin. Ownership and duplicate-name/hierarchy checks remain on the server.


## Consultation layout

Categories has one grouped list, initially collapsed. Search stays in the compact
consultation bar; level and type are native short choices inside More filters.
The summary and Clear reserve their own control slots. Opening criteria adds
fields below the rail, without moving the summary or resizing the search.
Controls stay mounted during live updates; Clear, native submissions and browser
Back/Forward retain the shared live-filter behavior.

The graph and view switch have been removed. Legacy `?view=tree` and other view
parameters render the same owned list and keep compatible filters. They do not
change stored category relationships, transactions or financial values.
