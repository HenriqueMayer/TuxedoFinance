# Architecture

The current architecture for Tuxedo Finance uses Django's full-stack delivery
model and explicit banking and ledger domain concepts.

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
| Supported runtime | Django development server (`runserver`) |
| Localization | Django gettext (`en`, `pt-br`) |

Public registration is a deployment-level policy, not a separate account model:
`ALLOW_SIGNUPS` is read from the process environment (default `True`). The
accounts signup view enforces it on every request, while public templates merely
mirror the state by showing or hiding signup calls to action. Existing login
flows are independent of this switch.

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
sandbox/       # non-persistent compensation and budget simulations
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
- `dashboard` query services compose the ledgers without posting records. Its
  views first call transaction synchronization, which can write derived banking
  records. The app owns no financial model.

Imports must avoid a model cycle. Cross-domain optional links that would create
one use string model references or a dedicated service boundary; posting an
event and its movements runs in one database transaction.

## Sources of truth

| Question | Source |
|---|---|
| What cash is available? | `BankAccount.opening_balance` + signed `BankMovement` amounts effective through the requested date. |
| What was income or expense? | Categorized `Transaction`. |
| What is owed on credit cards? | Derived `CardInvoice` totals and due-date movements; source purchases remain transactions, loyalty purchases, or redemption IOF. |
| What investment quantity is held? | `Investment`. |
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
`Transaction` rows. Invoice status is derived from the due date and the
synchronization cutoff; it is not confirmation from an external bank.

This keeps a local installation synchronized without a scheduler. As records
and recurrence history grow, measure request latency, query counts, and SQLite
write-lock time before changing the synchronization boundary. No asynchronous
worker, cache, or extra service is required by the current repository structure.

## Posting workflows

Services, rather than views or templates, own atomic posting:

1. **PIX/debit/account transaction:** validate ownership and currency; save
   the categorized transaction and synchronize its effective-date movement atomically.
2. **Credit transaction:** save the source transaction and synchronize invoice
   totals plus their due-date movements; create no purchase-date account debit.
3. **Invoice settlement:** create one due-date account debit and attach it to the
   invoice. Re-running is idempotent and cannot create a second settlement.
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
financial entities continue to use live/current rates until a future roadmap
item extends snapshot coverage. Editing amount, currency, fees, or date
refreshes the snapshot; descriptive edits preserve it.

## Routes

The route namespaces remain domain-based:

| Prefix | App | Scope |
|---|---|---|
| `/accounts/` | `accounts` | signup, login, POST logout, and authenticated preferences |
| `/dashboard/` | `dashboard` | overview and reports |
| `/transactions/` | `transactions` | categorized event CRUD/search |
| `/categories/` | `categories` | category CRUD |
| `/banking/` | `banking` | banks, accounts, ledger, PIX, cards, invoices, loyalty |
| `/investments/` | `investments` | portfolio, products, assets, operations, rates |
| `/sandbox/` | `sandbox` | authenticated, non-persistent salary planning |
| `/i18n/set_language/` | Django i18n | persist the selected interface language and redirect back |

All authenticated CBVs constrain root querysets to `request.user`; forms also
scope every foreign-key choice. Ownership is revalidated in posting services,
not assumed from browser options.

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

## Delivery and reset

Settings, middleware, authentication, precompiled Tailwind delivery and the
server-rendered request flow remain deliberately small and local-first. The
browser receives a versioned static stylesheet and never compiles utility
classes during navigation.
The current schema is intentionally incompatible with legacy financial data;
there is no dual-write or automatic conversion. See
[data-model.md](data-model.md#breaking-release).
