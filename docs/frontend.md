# Frontend: Design System & Templates

The approved banking release preserves the existing server-rendered Django
Template Language and precompiled TailwindCSS visual system. There is no SPA, JavaScript
framework or client-side chart library. Theme persistence, boosted link
navigation and HTMX chart-island swaps remain the deliberately narrow JavaScript
layer; every mutation is a normal CSRF-protected POST and every filter has a
plain GET fallback.

Tailwind CSS is generated ahead of time into `static/css/app.css`, so full-page
navigation never waits for browser-side class discovery or CSS compilation. The
generated file is versioned with the application and does not require Node/npm
at runtime. After changing Tailwind classes or tokens, rebuild it from
`assets/css/tailwind.css` with the standalone Tailwind CSS 3.4.17 CLI:

```bash
tailwindcss -c tailwind.config.js -i assets/css/tailwind.css -o static/css/app.css --minify
```

Bump the `?v=` query string in `base.html` whenever the generated stylesheet
changes so long-lived browser caches cannot retain the previous design.

Same-origin links inherit `hx-boost` from the page shell. HTMX keeps the current
document visible while it requests the next server-rendered page, then replaces
the body and updates browser history. Native links remain the fallback whenever
JavaScript or the HTMX CDN is unavailable. Forms explicitly opt out of boosting,
so POST, CSRF, validation, uploads, locale changes and redirects keep their
ordinary Django behavior. Full-page swaps move focus to the new `h1`; report and
investment chart islands keep their existing focus and scroll restoration.

## Visual language

The interface follows the final Haven & Hound design language documented in
`design-system/tuxedo-final-design-system.html`: cream and forest foundations,
caramel actions, distinct semantic colors, rounded surfaces and Inter 400–700
throughout. Light cards use white surfaces and soft shadows; dark cards use flat
forest surfaces over the forest-deep page background. Body copy starts at
16/24px, supporting copy at 14/20px, and compact labels never fall below 12px.

| Role | Semantic treatment |
|---|---|
| Income / account credit | `income` #176B52; dark `income-light` #64D8B1 |
| Expense / account debit / negative | `expense` #B42318; dark `expense-light` #FF8A80 |
| Investment | `investment` #7C5C13; dark `investment-light` #F4C95D |
| Installment plan | `installment` #6B4E8A; dark `installment-light` #C4A7E7 |
| Fixed recurrence | `fixed` #A65300; dark `fixed-light` #FFB45C |
| One-off purchase | `oneoff` #52605A; dark `oneoff-light` #B8C0BC |
| Own transfer | Neutral forest/cream; never income/expense colored |
| Credit-card payable | Caramel |
| Warning / overdue invoice | Caramel plus explicit text/icon |

Color is never the only carrier of status. Monetary labels always include a
currency symbol or ISO code, especially when native and base values are shown
together.

The navigation brand combines `tuxedo-mark-256.png` with a two-line uppercase
wordmark: `Tuxedo` in the foreground color and `Finance` in caramel. Primary
actions are solid caramel pills with forest-deep text; `caramel-ink` carries
brand links over light surfaces. Outline actions invert to forest/cream on
hover. Titles, labels, controls and tabular monetary figures all use Inter.
Secondary text uses at least forest/70 or cream/70 contrast.

## Root layout and navigation

`templates/base.html` continues to own the page shell, theme setup, public or
authenticated navbar, messages, content block and footer. The authenticated
navigation becomes:

```text
Dashboard | Transactions | Categories | Banking | Investments | Reports
```

`Banking` remains active for nested bank, account, card, invoice, movement and
loyalty routes. The mobile navigation is a full-screen forest-deep overlay with
the same links and ordering as desktop. It slides in and locks page scrolling
while open.

`partials/language_selector.html` is included once in each active navbar. It
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

Money rendering follows the authenticated user's base reporting currency.
Historical transfer and investment totals identify their persisted FX snapshot;
other current valuations show their valuation date and rate source.

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

Transaction entry uses progressive enhancement: server-rendered selects are the
authoritative no-JavaScript path, while JavaScript reveals the fields relevant
to the selected payment channel and enhances category search. Hidden client-side
controls never replace server-side ownership and compatibility validation.

Forms use the established `form_field.html`, validation summary, forest/cream
inputs with caramel focus, and the Save/Cancel pill action pattern. Checkboxes
use `accent-caramel`. Server-side validation remains authoritative.

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

The UI uses the authenticated user's `UserPreference.base_currency`, selected
from Settings. Changing it updates consolidated presentation only; native
amounts remain unchanged. Transfer/investment historical snapshots and current
valuations are visibly distinct, and missing rates are shown explicitly as
incomplete.

Inputs remain dot-decimal HTML number fields. Display localization follows each
currency's formatting metadata; SVG coordinates and CSS percentages remain
unlocalized.

UI language does not choose currency formatting. `core/formats/en/` and
`core/formats/pt_BR/` both delegate separators to the selected currency, so a
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

- Current Balance (realized cash)
- Income this month
- Expenses this month
- Investments this month
- Balance this month
- Projected balance at the end of the month

Current Balance remains distinct from the projected month-end close. Credit-card
purchases belong to the statement month but affect cash only when the invoice is
settled. Own transfers may appear in activity but are visually neutral and
absent from income/expense charts. Projected figures are labeled and never
presented as posted cash.

## Reports and charts

Charts remain inline server-rendered SVG/CSS with native `<title>` tooltips,
forest/cream tooltip pills, responsive overflow containers and accessible text
summaries. Income uses the green pair, expense uses the red pair, and
investment has its own ochre pair. The recurrence donut uses purple
installments, orange fixed recurrences and neutral one-off purchases; its zero
line is neutral. HTMX swaps only the report island while preserving focus and
viewport; plain links/forms remain equivalent.

Every chart states its reporting currency and actual versus projected period.
The selected per-user base currency, snapshot status where supported, and
explicit missing-FX totals are shown. Current valuation charts display their
valuation date/source.

Credit purchase and invoice payment series must use distinct labels. No chart
may aggregate both as expenses. Investment yield is shown in investment
performance, not bank income.

## Responsiveness and accessibility

All pages remain mobile-first. Wide ledgers, invoice item tables and charts use
internal horizontal scrolling rather than forcing body overflow. Bank/account
hierarchies collapse to stacked cards on small screens. Labels, status text,
focus rings, keyboard navigation and confirmation screens remain available
without relying on hover, color or JavaScript.
