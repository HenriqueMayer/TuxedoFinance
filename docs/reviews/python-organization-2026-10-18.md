# Python responsibility organization — 2026-10-18

This is the third agreed organization lot, based on `98d98d4`. It reorganizes
Python responsibilities within the existing apps and preserves the supported
installation, domain behavior and data. The earlier
[tooling/browser organization](repository-organization-2026-10-18.md) remains a
separate delivery.

## Module boundaries

Banking forms now have owners for shared fields/ownership, accounts, cards,
invoices, loyalty, transfers and exchange rates. Banking views separate those
workflows from workspace presentation and shared form lifecycle. Investments
forms/views distinguish operations, portfolio consultation, product/asset setup
and local price observations. Transactions views distinguish consultation/CSV
export from editing and category-split controls.

Explicit package exports preserve public imports such as
`banking.forms.CreditCardForm`, `investments.views.AssetCreateView` and
`transactions.views.TransactionListView`. Internal modules import their actual
dependencies directly; there is no proxy layer for mutable globals. The owning
[Banking](../apps/banking.md), [Investments](../apps/investments.md) and
[Transactions](../apps/transactions.md) guides record the file maps.

Category CSV parsing, input limits and atomic hierarchy insertion now belong to
`categories.importing`; views retain authentication, HTTP handling, recoverable
errors and messages. The parser is unchanged. The insertion body is unchanged
apart from accepting the authenticated user as an explicit argument in place of
`request.user`.

The other cohesive modules remain intact. In particular, financial services,
model classes, migration history, positions/replay and URL configurations keep
their existing code and paths. No app moved into a new top-level container and
no schema or data migration is required by this lot. Templates, UI strings,
JavaScript and committed CSS are unchanged.

## Test ownership and discovery

All eleven apps now own a `tests/` package. The former 73 flat test source files
are organized into 109 focused `test_*.py` modules; shared fixtures, factories,
statement samples, snapshots and query classifiers live in named support
modules. Each package initializer stays free of test-class imports, avoiding
duplicate unittest discovery. The [test index](../../tests/README.md) documents
module selection and shared helper ownership.

Discovery before and after contains the same 723 unique app/class/method
identities. All 127 original class definitions remain present. Their ASTs are
identical after normalizing only seven banking mock lookup strings and four
repository-parent expressions in settings subprocess tests. Decorators and
assertions remain intact. Cross-test imports now name support modules rather
than importing another discovered test module.

Mocks follow their actual lookup owner: bank workspace synchronization belongs
to `banking.views.workspace`, and invoice synchronization to
`banking.views.invoices`. Public view exports preserve imports but do not
redirect patches to implementation globals. Root resolution in settings tests
accounts for their new package depth.

## Validation

Local validation uses synthetic data, temporary installation paths and an empty
environment file. Browser tests use only `npm run test:e2e` and its owned
loopback server/database. Existing installation data, environments, backups and
dependencies were not relocated or removed.

The complete Django traversal exercised all 723 cases. It initially recorded
722 passes and one failure because an invoice mock still targeted the workspace
module already imported by the running suite. After correcting that lookup,
all ten cases in the affected module passed in a focused isolated rerun. The
723-case result combines that traversal and recovery; it does not count the
repeated cases as additional tests.

| Check | Observed result |
|---|---|
| Version consistency, Django system check, migration check | Passed; no pending model changes. |
| Django cases | 723 unique cases passed after the complete traversal and focused module recovery. |
| Combined line/branch coverage | 95%, using the existing scope including executed tests/migrations and the unchanged 70% floor. |
| Python repository-tool tests | 32 passed. |
| JavaScript amount/allocation tests | 16 passed. |
| Focused application browser cases | 29 unique cases passed after the targeted traversal and native-animation readiness recovery. |
| Django discovery | Same 723 unique app/class/method identities; no lost or duplicated cases. |
| Source preservation | 69 recorded model/migration/URL/service/position files match the starting hashes; moved definitions retain their bodies. |
| CSS rebuild | Byte-identical to the committed stylesheet. |
| Lock consistency, focused Ruff rules, local documentation references and whitespace | Passed. |

The browser selection covers bank/account actions, invoice and FX filters,
category hierarchy/CSV recovery, investment operations/setup/prices and
transaction splits/payment validation, using desktop/phone viewports, both
themes and native submissions. Its first traversal passed 28 cases; one native
mobile case timed out during a click while the account panel was animating.
The isolated rerun and a tracked-source control at `98d98d4` reproduced the same
block before any form-opening request reached the server. The trace stopped
inside Playwright's click retry after detecting the existing entry animation.
The test now polls the actual panel transform from the runner before clicking;
it retains the animation, real click and all original navigation/selection
assertions. No forced click, arbitrary sleep or application change was used.
The focused recovery replaces that earlier result rather than adding a case to
the 29-case selection.

Coverage outputs remain under `.local/coverage/`; local validation logs remain
under `.local/test-results/python-organization/`. Raw comparison inventories and
AST evidence were inspected locally and are not runtime dependencies.

## Limits and remaining work

This lot does not claim a performance improvement or new functionality. It does
not implement the later frontend/document splitting lot. Physical mobile
devices, other browser engines, real Docker execution, dependency vulnerability
audits, remote CI and publication/release checks are outside this validation.
The complete application browser suite and public static-tour suite are not
repeated for these Python-only changes.
