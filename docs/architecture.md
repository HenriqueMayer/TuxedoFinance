# Architecture

The current architecture for Tuxedo Finance uses Django's full-stack delivery
model and explicit banking and ledger domain concepts.
This guide covers the `0.10.0` release baseline and the implemented Unreleased
local-finance evolution; it does not imply that branch changes are published.

## Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Framework | Django 6 full stack |
| Frontend | Django Template Language + TailwindCSS |
| Database | SQLite |
| Authentication | Native `django.contrib.auth` |
| Dependency management | `uv` |
| Views | Class-based views plus focused function views for imports, exports, and bulk actions |
| Supported runtime | Native `runserver`; Docker with Gunicorn and WhiteNoise |
| Localization | Django gettext (`en`, `pt-br`) |

Public registration is a deployment-level policy, not a separate account model:
`ALLOW_SIGNUPS` is read from the process environment (default `True`). The
accounts signup view enforces it on every request, while public templates merely
mirror the state by showing or hiding signup calls to action. Existing login
flows are independent of this switch.

Docker uses one non-root web container with a local named SQLite volume and
loopback-only port publication by default. Static assets are collected at build
time; migrations run before the single server starts. See [Docker operations](docker.md).

## Domain apps

```text
core/          # settings, root URLs, currency registry and shared formatting
pages/         # public landing page
accounts/      # authentication and presentation preferences
categories/    # income and expense classification
banking/       # banks, accounts, movements, PIX, cards, invoices and loyalty
transactions/  # categorized economic events and recurrence schedules
dashboard/     # ledger, cash-flow, invoice and net-worth read models
investments/   # products, assets, position operations and valuation
planning/      # category budgets, existing-cash goals and local review signals
ingestion/     # explicitly reviewed local statements and guarded import undo
sandbox/       # private planning drafts and isolated simulations
```

`banking/` owns every settlement instrument and the account ledger. `Bank` is
shared with `investments`.

## Dependency direction

```text
dashboard views ──> transactions synchronization ──> banking models
       │
       └──> dashboard queries ──> banking / transactions / investments
transactions models ──> banking / categories
investments ──> banking
banking views ──> transactions synchronization

Arrows mean "calls or imports", not ownership.
```

- `banking` owns settlement truth and can exist without categorized transactions.
- `transactions` references banking instruments to describe how an economic
  event settles; it does not calculate account balances.
- `investments` reuses `Bank` and `BankAccount` for providers and cash legs, but
  keeps its position ledger independent from `Transaction`.
- `planning` owns limits, earmarks and review decisions, reading existing
  transactions and cash sources without posting financial activity.
- `ingestion` owns statement evidence and import decisions. Only explicit
  confirmation calls canonical transaction, payment or transfer services;
  matching an existing movement does not create a second source.
- `dashboard` query services compose the ledgers without posting records. Its
  views first call transaction synchronization, which can write derived banking
  records. The app owns no financial model.

Imports must avoid a model cycle. Cross-domain optional links that would create
one use string model references or a dedicated service boundary; posting an
event and its movements runs in one database transaction.

## Sources of truth

| Question | Source |
|---|---|
| What cash is available? | The applicable dated `BankAccount` opening + signed `BankMovement` amounts effective through the requested date. |
| What was income or expense? | Categorized `Transaction`, with exact `TransactionSplit` allocations when present. |
| What is billed on credit cards? | Derived `CardInvoice` totals; default automatic due-date movements or explicitly confirmed manual `InvoicePayment` rows. |
| What card debt is incurred at a date? | Purchase and realized recurrence sources through that date, including future installments, less effective settlements; excess payment remains card credit. |
| What investment quantity and cost are held? | Dated opening plus chronological `Investment` replay per product/asset; unit disposals remove weighted cost, not signed proceeds. |
| What is a position worth at a date? | Remaining quantity × latest local `PriceObservation` by that date, or disclosed remaining-cost fallback; monetary positions use their balance. |
| What is reserved for a goal? | `GoalAllocation` backed by existing positive account/cash-pot balances; no new financial asset is created. |
| What did an imported statement establish? | Owned `ImportBatch`/`ImportedRow` evidence and explicit source links, not a replacement bank ledger. |
| How many loyalty points exist? | Signed `LoyaltyEntry` rows. |
| What was a transfer or investment worth historically? | Its persisted FX snapshot, including source/target currencies, rate, effective date, and status. |
| What is another amount worth now? | User's `UserPreference.base_currency` plus a current `ExchangeRate`, shown as a labeled current valuation. |

This separation prevents credit purchases from reducing cash before the invoice
is paid and prevents the later invoice debit from counting the same spending a
second time.

## Request-time synchronization

`transactions.services.sync_user_ledger` owns the idempotent projection of
transactions into banking movements and card invoices. Transaction mutations
call it within an atomic save/delete workflow. Dashboard and report views, bank
list/account detail views, and relevant loyalty operations also invoke it.
These page reads can therefore update, create, or delete derived rows.

The default projection horizon is twelve months beyond today. Future-effective
movements may already exist in storage; balance queries filter by effective
date so they do not become realized cash early. Recurrences derive movements
and invoice amounts from their source transaction, without creating additional
`Transaction` rows. Default automatic invoice status is derived from the due
date and synchronization cutoff, not confirmation from an external bank.
Cards may opt into manual settlement from a due-date boundary; those invoices
have no projected settlement movement and derive status from explicit payments.
Manual mode is sticky per invoice so later settings changes do not erase
confirmed evidence. Payment-bearing invoices survive source/horizon cleanup.

The projection compares existing movements and invoices to their desired
fields, saving only changed values and deleting only stale derived rows.
Repeated unchanged synchronization retains identifiers and timestamps and
does not repeat unchanged writes. It still reads and folds source history;
this is diff reconciliation, not incremental event processing or a persisted
cache. Atomic workflows and `select_for_update` support row locking where the
database provides it. SQLite serializes writers; neither that call nor fewer
writes makes concurrent SQLite writers independent.

This keeps a local installation synchronized without a scheduler. As records
and recurrence history grow, measure request latency, query counts, and SQLite
write-lock time before changing the synchronization boundary. No asynchronous
worker, cache, or extra service is required by the current repository structure.

## Posting workflows

Services, rather than views or templates, own atomic posting:

1. **PIX/debit/account transaction:** validate ownership and currency; save
   the categorized transaction and synchronize its effective-date movement atomically.
2. **Credit transaction:** save the source transaction and synchronize invoice
   totals plus automatic due-date movements where applicable; create no
   purchase-date account debit.
3. **Invoice settlement:** default automatic mode creates one due-date debit.
   Optional manual confirmation atomically saves `InvoicePayment` and its
   actual-date debit, with a unique confirmation UUID preventing repeat posting.
   Partial payment changes settlement evidence, not the source purchase amount.
4. **Own transfer:** create two movements sharing a transfer identifier. The
   movements use kind `TRANSFER`, not income/expense; cross-currency pairs retain both
   native amounts and their persisted FX snapshot when conversion is available.
5. **Investment deposit/withdrawal:** create the `Investment` and its required
   account movement or points-ledger entry atomically. Deposits accept exactly
   one account or loyalty-program source; withdrawals require a destination
   account. Yield remains internal.
6. **Loyalty redemption:** create a `RewardRedemption`, its points debit and the
   target-account reward credit atomically. Account-funded IOF posts immediately;
   credit-card IOF enters the invoice synchronization path.
7. **Statement import:** stage and review bounded local evidence without
   financial mutation; confirm all explicit decisions atomically through these
   same source services and synchronize once. Matching posts nothing. Guarded
   undo deletes only unchanged sources created by that import.
8. **Budget/goal/quote:** save owned limits, reservations or local prices without
   a cash posting. A quote changes valuation evidence; a goal names a portion of
   existing cash. Neither is income or an additional bank movement.

Personal financial entries are editable; audit-grade reversal workflows are out
of scope.

## Multicurrency

`accounts.UserPreference.base_currency` selects the reporting currency for the
authenticated user. The preference is initialized to BRL for new and existing
users and is changed through the authenticated Settings route. Accounts and
events retain native currencies and amounts; changing the preference affects
presentation totals only. Services return native totals plus converted totals
and explicit missing-rate metadata. They never add unlike currencies directly.
Bank transfers and investment operations that require conversion persist an FX
snapshot. Missing rates preserve native data and produce an explicit incomplete
status. Existing transfers and investments are reconstructed only where an
authoritative rate provides evidence; otherwise no rate is invented. Other
financial entities use labeled read-time conversion, at the current or selected
cutoff date, until a future scope extends captured snapshot coverage. Editing
amount, currency, fees, or date refreshes the snapshot; descriptive edits preserve it.

`banking.services.ConversionContext` caches pair/date lookup results within one
owned request, including missing evidence, and rejects reuse for another user.
Dashboard composition and portfolio series can share it. It is not a global
rate cache and cannot replace an operation's captured FX evidence. Dated account,
card and quote valuations request the cutoff rate; cost-based historical
investment components retain their operation evidence. Missing valuation or
performance evidence is carried separately rather than silently summed away.

Report chart islands also reuse a single request-local list of categorized
sources and prefetched splits. Services reject shared lists containing another
user's records. Each island still applies its own month/window filters; this is
read reuse, not an authoritative or persisted financial cache. The
[project health review](reviews/project-health-2026-10-16.md#reproducible-reporting-measurements)
records the measured cost and limits.

New nonzero account and asset openings require dates. Incremental migrations
leave older unknown opening dates null, retaining current holdings with an
explicit incomplete-baseline warning. Replay and derived read models are
editable reconstructions, not immutable statement snapshots; they do not infer
annualized or cash-flow-adjusted returns.

## Routes

The route namespaces remain domain-based:

| Prefix | App | Scope |
|---|---|---|
| `/accounts/` | `accounts` | signup, login, POST logout, and authenticated preferences |
| `/dashboard/` | `dashboard` | overview and reports; dated-wealth interface paused |
| `/transactions/` | `transactions` | categorized event CRUD/search |
| `/categories/` | `categories` | category CRUD |
| `/banking/` | `banking` | banks, accounts, ledger, PIX, cards, invoices, loyalty |
| `/investments/` | `investments` | portfolio, products, assets, operations, local prices and charts |
| `/planning/` | `planning` | operational budgets, backed goals, reservations and local signals |
| `/imports/` | `ingestion` | paused CSV/OFX operations; owned posted history remains read-only |
| `/sandbox/` | `sandbox` | authenticated planning workspace and explicit draft persistence |
| `/i18n/set_language/` | Django i18n | persist the selected interface language and redirect back |

All authenticated CBVs constrain root querysets to `request.user`; forms also
scope every foreign-key choice. Ownership is revalidated in posting services,
not assumed from browser options.

`core.features.review_gate` checks paused operation routes on GET and POST;
hiding a navigation link is not the gate. Current default settings keep imports
and the net-worth interface paused, while their financial sources and read
models remain intact. Follow the [roadmap](roadmap.md) and owning app guides
for availability; do not infer it from a model or URL pattern alone.

## Localization request flow

`SessionMiddleware` runs before `LocaleMiddleware`. The locale middleware uses
Django's native language cookie when present, otherwise negotiates the initial
supported language from the browser and falls back to English. It activates the
language before URL resolution and view/template rendering, including HTMX
fragment requests. The URLconf deliberately does not use `i18n_patterns()`, so
all domain URLs remain stable across languages.

Translation concerns stop at fixed interface and system copy. Python uses
`gettext_lazy` for deferred declarations and `gettext` at runtime; templates
use `translate` and `blocktranslate`. The project-level Portuguese catalog is
`locale/pt_BR/LC_MESSAGES/django.po`/`django.mo`. The nine default category
names are resolved once through gettext in the language active when the account
is created, then stored as ordinary user-owned data. Existing and user-entered
categories are never translated automatically. Currency is a separate axis:
parallel `core.formats.en` and
`core.formats.pt_BR` modules both resolve separators from currency metadata.

## Delivery and compatibility

Settings, middleware, authentication, precompiled Tailwind delivery and the
server-rendered request flow remain deliberately small and local-first. The
browser receives a versioned static stylesheet and never compiles utility
classes during navigation.
Released installations use incremental migrations that preserve their records.
The original pre-release clean reset is historical and does not apply to ordinary
updates. See [release compatibility](data-model.md#release-compatibility).
