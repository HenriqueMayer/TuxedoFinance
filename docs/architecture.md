# Architecture

The approved target architecture for CashFlow. The Django full-stack delivery
model remains unchanged; the domain boundary changes from generic payment
methods to explicit banking and ledger concepts.

## Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Framework | Django 6 full stack |
| Frontend | Django Template Language + TailwindCSS |
| Database | SQLite |
| Authentication | Native `django.contrib.auth` |
| Dependency management | `uv` |
| Views | Class-Based Views |
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
accounts/      # authentication
categories/    # income and expense classification
banking/       # banks, accounts, movements, PIX, cards, invoices and loyalty
transactions/  # categorized economic events and recurrence schedules
dashboard/     # ledger, cash-flow, invoice and net-worth read models
    investments/   # products, assets, position operations and valuation
```

`banking/` owns every settlement instrument and the account ledger. `Bank` is
shared with `investments`.

## Dependency direction

```text
categories ────────┐
                   v
banking <──── transactions ────> dashboard
   ^                                  ^
   └──────── investments ─────────────┘
```

- `banking` owns settlement truth and can exist without categorized transactions.
- `transactions` references banking instruments to describe how an economic
  event settles; it does not calculate account balances.
- `investments` reuses `Bank` and `BankAccount` for providers and cash legs, but
  keeps its position ledger independent from `Transaction`.
- `dashboard` is read-only composition over all three ledgers. It owns no
  financial records.

Imports must avoid a model cycle. Cross-domain optional links that would create
one use string model references or a dedicated service boundary; posting an
event and its movements runs in one database transaction.

## Sources of truth

| Question | Source |
|---|---|
| What cash is available? | `BankAccount.opening_balance` + `BankMovement`. |
| What was income or expense? | Categorized `Transaction`. |
| What is owed on credit cards? | `CardInvoice` and its items/payments. |
| What investment quantity is held? | `InvestmentOperation`. |
| How many loyalty points exist? | `LoyaltyEntry`. |
| What was a transfer or investment worth historically? | Its persisted FX snapshot, including source/target currencies, rate, effective date, and status. |
| What is another amount worth now? | User's `UserPreference.base_currency` plus a current `ExchangeRate`, shown as a labeled current valuation. |

This separation prevents credit purchases from reducing cash before the invoice
is paid and prevents the later invoice debit from counting the same spending a
second time.

## Posting workflows

Services, rather than views or templates, own atomic posting:

1. **PIX/debit/account transaction:** validate ownership and currency; create
   the categorized transaction and immediate movement atomically.
2. **Credit transaction:** create the transaction as an invoice item; create no
   account movement.
3. **Invoice settlement:** create one due-date account debit and attach it to the
   invoice. Re-running is idempotent and cannot create a second settlement.
4. **Own transfer:** create two movements sharing a transfer identifier. The
   event is `TRANSFER`, not income/expense; cross-currency pairs retain both
   native amounts and their persisted FX snapshot when conversion is available.
5. **Investment deposit/withdrawal:** create the position operation and required
   source/destination account movement atomically. Yield remains internal.
6. **Loyalty redemption:** post the points entry and, when IOF applies, settle it
   through the selected funding instrument using its normal immediate or invoice
   path.

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
item extends snapshot coverage. Editing amount, currency, or date refreshes the
snapshot.

## Routes

The route namespaces remain domain-based:

| Prefix | App | Scope |
|---|---|---|
| `/dashboard/` | `dashboard` | overview and reports |
| `/transactions/` | `transactions` | categorized event CRUD/search |
| `/categories/` | `categories` | category CRUD |
| `/banking/` | `banking` | banks, accounts, ledger, PIX, cards, invoices, loyalty |
| `/investments/` | `investments` | portfolio, products, assets, operations, rates |
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
`locale/pt_BR/LC_MESSAGES/django.po`/`django.mo`. Persisted domain and user data,
including categories, are not looked up in gettext and therefore remain
language-neutral. Currency is a separate axis: parallel `core.formats.en` and
`core.formats.pt_BR` modules both resolve separators from currency metadata.

## Delivery and reset

Settings, middleware, authentication, Tailwind CDN delivery and the
server-rendered request flow remain deliberately small and local-first.
The current schema is intentionally incompatible with legacy financial data;
there is no dual-write or automatic conversion. See
[data-model.md](data-model.md#breaking-release).
