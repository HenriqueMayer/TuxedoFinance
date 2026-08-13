# Frontend: Design System & Templates

The approved banking release preserves the existing server-rendered Django
Template Language and TailwindCSS visual system. There is no SPA, JavaScript
framework or client-side chart library. Theme persistence and HTMX chart-island
swaps remain the deliberately narrow JavaScript layer; every mutation is a
normal CSRF-protected POST and every filter has a plain GET fallback.

## Visual language

The light/dark theme, Inter typography, rounded bordered surfaces, gradient
primary actions and semantic finance colors remain consistent across the new
screens.

| Role | Semantic treatment |
|---|---|
| Income / account credit | Emerald |
| Expense / account debit | Rose |
| Investment | Amber |
| Own transfer | Indigo/neutral; never income/expense colored |
| Credit-card payable | Violet |
| Warning / overdue invoice | Amber plus explicit text/icon |

Color is never the only carrier of status. Monetary labels always include a
currency symbol or ISO code, especially when native and base values are shown
together.

## Root layout and navigation

`templates/base.html` continues to own the page shell, theme setup, public or
authenticated navbar, messages, content block and footer. The authenticated
navigation becomes:

```text
Dashboard | Transactions | Categories | Banking | Investments | Reports
```

`Banking` remains active for nested bank, account, card, invoice, movement and
loyalty routes. The mobile `<details>/<summary>` menu uses the same links and
ordering as desktop.

`partials/language_selector.html` is included once in the public navbar and in
both authenticated variants: the desktop controls and CSS-only mobile menu. It
posts the current path and `en` or `pt-br` to Django's
`/i18n/set_language/`; JavaScript submits on change and the `noscript` Apply
button preserves the server-rendered fallback. The choice is stored in Django's
language cookie, not local storage or the user model, and URLs have no locale
prefix.

## Template tree

```text
templates/
├── base.html
├── partials/
│   ├── navbar_public.html   navbar_app.html
│   ├── footer.html          messages.html
│   ├── form_field.html      stat_card.html
│   ├── language_selector.html theme_toggle.html
│   └── empty_state.html
├── pages/                   accounts/        categories/
├── banking/
│   ├── list.html            detail.html
│   ├── form.html            confirm_delete.html
│   └── exchange_rates.html
├── transactions/
├── dashboard/
└── investments/
```

Money rendering follows the project reporting currency. Per-user base currency
and retained historical FX states are planned for ROADMAP Phases 3 and 4.

## Banking information architecture

`/banking/` starts with bank cards. Each bank expands into accounts showing
account name, native currency, opening balance, posted balance, PIX status and
linked cards. The account detail is organized in this order:

1. Available balance and native currency.
2. Primary actions: new transaction and own transfer.
3. PIX capability and debit/credit cards.
4. Movement ledger with date, direction, kind, related event and running balance.
5. Credit invoices and due/overdue status.

Opening balance is clearly labeled as the ledger starting point, not an income
transaction. Personal records remain editable; audit-grade reversal controls
are not part of the current product.

## Forms and settlement disclosure

Forms use the established `form_field.html`, validation summary, standard input
classes and Save/Cancel action pattern. Server-side validation remains
authoritative.

- PIX/account/debit choices state `Affects account balance immediately`.
- Credit card choices state `Added to the card invoice; account debited on due date`.
- Own transfer forms identify source and destination, show both currencies, and
  explain that the transfer is not income or expense.
- Credit transaction forms show the target invoice/due date when known.
- Investment deposit forms require `Source account`; withdrawals require
  `Destination account`; yield forms state `Internal yield, no bank movement`.
- Loyalty redemption forms show points, target monetary amount/currency, IOF and
  IOF funding instrument as one reviewable cost block.

Conditional inputs may be rendered in full with server-side validation when a
zero-JS interaction would otherwise hide required accounting context. HTMX may
enhance dependent choices, but the submitted form must work without it.

## Multicurrency display

The current UI uses the project reporting currency. Per-user base currency,
historical conversion evidence and missing-rate presentation are planned for
ROADMAP Phases 3 and 4.

Inputs remain dot-decimal HTML number fields. Display localization follows each
currency's formatting metadata; SVG coordinates and CSS percentages remain
unlocalized.

UI language does not choose currency formatting. `core/formats/en/` and
`core/formats/pt_BR/` both delegate separators to the configured currency, so a
language switch cannot turn a correctly formatted amount into a mixed
symbol/separator representation.

## Translation convention

All new fixed interface copy must be marked at its source: `gettext_lazy` for
deferred Python declarations, `gettext` for runtime Python messages,
`{% translate %}` (the modern spelling of `{% trans %}`) for short template
strings and `{% blocktranslate %}` for longer copy or interpolated values.
Update and compile the `pt_BR` gettext catalog after changing marked strings.
Dynamic values are not translation
keys: category/subcategory names and all other user-entered titles, notes,
institutions and financial data render verbatim.

HTMX report and investment chart islands need no separate locale mechanism.
Their requests retain the language cookie, pass through `LocaleMiddleware` and
render translated fragments in the active request language.

## Dashboard

Stat cards separate concepts instead of collapsing them into one balance:

- Available cash
- Income this month
- Expenses this month
- Credit-card payable
- Investments
- Net worth

Account cash cards drill into the movement ledger. Invoice payable cards drill
into open invoices. Own transfers may appear in activity but are visually
neutral and absent from income/expense charts. Projected figures are labeled and
never presented as posted cash.

## Reports and charts

Charts remain inline server-rendered SVG/CSS with native `<title>` tooltips,
responsive overflow containers and accessible text summaries. HTMX swaps only
the report island while preserving focus and viewport; plain links/forms remain
equivalent.

Every chart states its reporting currency and actual versus projected period.
Per-user base currency, valuation dates and missing-FX totals are planned for
ROADMAP Phases 3 and 4.

Credit purchase and invoice payment series must use distinct labels. No chart
may aggregate both as expenses. Investment yield is shown in investment
performance, not bank income.

## Responsiveness and accessibility

All pages remain mobile-first. Wide ledgers, invoice item tables and charts use
internal horizontal scrolling rather than forcing body overflow. Bank/account
hierarchies collapse to stacked cards on small screens. Labels, status text,
focus rings, keyboard navigation and confirmation screens remain available
without relying on hover, color or JavaScript.
