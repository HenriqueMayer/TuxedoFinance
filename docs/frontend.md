# Frontend: Design System & Templates

The current design-system release preserves the server-rendered Django
Template Language and precompiled Tailwind CSS visual system. There is no SPA, JavaScript
framework or client-side chart library. Theme persistence, boosted link
navigation and HTMX chart-island swaps remain the deliberately narrow JavaScript
layer. User-submitted mutations use CSRF-protected POSTs, and filters have
plain GET fallbacks. Some page reads synchronize derived ledger records before
rendering; see [request-time synchronization](architecture.md#request-time-synchronization).

Tailwind CSS is generated ahead of time into `static/css/app.css`, so full-page
navigation never waits for browser-side class discovery or CSS compilation. The
generated file is versioned with the application and does not require Node/npm
at runtime. Frontend tooling is pinned in `package.json`/`package-lock.json` for
development and CI. Follow the [frontend build workflow](../CONTRIBUTING.md#frontend-and-translations)
after changing Tailwind classes or tokens.

Bump the `?v=` query string in `base.html` whenever the generated stylesheet
changes so long-lived browser caches cannot retain the previous design.

Same-origin links inherit `hx-boost` from the page shell. HTMX keeps the current
document visible while it requests the next server-rendered page, then replaces
the body and updates browser history. Native links remain the fallback whenever
JavaScript is unavailable. Mutating forms, uploads, locale changes, logout and
download links explicitly opt out of boosting, so POST, CSRF, validation and
file responses keep their ordinary Django behavior. GET filter forms may use
HTMX when they target a documented page or island update. Full-page swaps move
focus to the new `h1`; report and investment chart islands keep their existing
focus and scroll restoration. The
investment movement island updates filters and pagination independently, then
returns to the beginning of the movement section instead of the top of the page;
plain GET links and the section anchor provide the same no-JavaScript fallback.

## Visual language

The interface follows the Tuxedo Finance design language documented in
`design-system.html`: cream and forest foundations,
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
wordmark: `Tuxedo` in the foreground color and `Finance` in caramel. It always
links to the public landing page, including for authenticated users. Primary
actions are solid caramel pills with forest-deep text; `caramel-ink` carries
brand links over light surfaces. Outline actions invert to forest/cream on
hover. Titles, labels, controls and tabular monetary figures all use Inter.
Secondary text uses at least forest/70 or cream/70 contrast.

## Root layout and navigation

`templates/base.html` continues to own the page shell, theme setup, public or
authenticated navbar, messages, content block and footer. The authenticated
navigation becomes:

```text
Dashboard | Reports | Transactions | Categories | Banks | Investments
```

`Banks` remains active for nested bank, account, card, invoice, movement and
loyalty routes. The authenticated desktop navigation starts at the `xl`
breakpoint so tablet and narrow-laptop widths do not compress or overflow the
full link set. Below that breakpoint, the mobile navigation is a full-screen
forest-deep modal with the same links and ordering as desktop. It slides in,
locks page scrolling, makes background content inert, contains keyboard focus,
closes on Escape and restores focus to its trigger.

`partials/language_selector.html` is included once in each active navbar. It
posts the current path and `en` or `pt-br` to Django's
`/i18n/set_language/`; JavaScript submits on change and the `noscript` Apply
button preserves the server-rendered fallback. The choice is stored in Django's
language cookie, not local storage or the user model, and URLs have no locale
prefix.

HTMX 2.0.10 is vendored at `static/js/vendor/htmx.min.js`; the application does
not contact a JavaScript CDN at runtime. CI verifies the vendored file against
the upstream release checksum before running browser smoke tests.

Django's content-security-policy middleware restricts script sources, forms,
images and connections to this installation. Inline scripts and styles remain
allowed because translated progressive-enhancement copy and server-calculated
chart geometry are rendered directly by Django templates; Google Fonts is the
only external presentation origin. Language selection uses a delegated local
listener instead of an inline event handler and retains its `noscript` submit.

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
├── dashboard/              sandbox/
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

Progressive disclosure is a project-wide interface rule, not a pattern limited
to one form. Every new or updated form, filter, picker, menu or categorized flow
must initially present only the information needed to make the current choice,
then reveal the fields and explanations that belong to the selected option or
category. Implementations must:

- hide inactive branches instead of leaving unrelated controls competing for
  attention;
- clear stale values from a branch when the user deliberately switches away
  from it, so hidden inputs cannot affect the submitted result;
- keep a branch visible when it contains a server-side validation error, giving
  the user a clear recovery path;
- announce useful selection consequences in text when they are not already
  evident from the visible labels;
- retain a complete server-rendered, no-JavaScript submission path and enforce
  ownership, compatibility and accounting rules on the server.

When an existing screen with conditional branches is changed, those branches
must be brought into this contract as part of the change. The loyalty-entry form,
for example, shows an invoice only for an invoice award, shows payment-source
and amount fields only for a points purchase, and shows neither branch for an
adjustment, expiration or redemption.

Forms use the established `form_field.html`, validation summary, forest/cream
inputs with caramel focus, and the Save/Cancel pill action pattern. Checkboxes
use `accent-caramel`. Server-side validation remains authoritative.

- PIX/account/debit choices state `Affects account balance immediately`.
- Credit card choices state `Added to the card invoice; account debited on due date`.
- Own transfer forms identify source and destination, show both currencies, and
  explain that the transfer is not income or expense.
- Credit transaction forms show the target invoice/due date when known.
- Loyalty invoice awards show only the related invoice; points purchases show
  only their payment source and amount. Switching kind clears the inactive
  branch.
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
The nine system-provided category names are translated once during account
creation and then stored as user-owned data. Other category/subcategory names
and all user-entered titles, notes, institutions and financial data are not
translation keys and render verbatim.

HTMX report and investment chart islands need no separate locale mechanism.
Their requests retain the language cookie, pass through `LocaleMiddleware` and
render translated fragments in the active request language.

## Dashboard

Stat cards separate concepts instead of collapsing them into one balance:

- available cash, selected-month balance change, and projected closing balance;
- income, expenses, investments, and withdrawals as separate performance cards;
- current-month values through today with the remaining plan shown underneath;
- complete values for past months and explicitly planned values for future months.

Current Balance remains distinct from the projected month-end close. Credit-card
purchases belong to the statement month but affect cash only when the invoice is
settled. Own transfers may appear in activity but are visually neutral and
absent from income/expense charts. Projected figures are labeled and never
presented as posted cash. A compact top-six category breakdown follows the same
month-to-date, completed-month, or planned-month context as the cards. Live bank
accounts and upcoming invoices are limited to five rows each and link to Banking
for the complete lists.

## Reports and charts

Charts remain inline server-rendered SVG/CSS with native `<title>` fallbacks,
forest/cream tooltip pills on mouse hover and keyboard focus, responsive
overflow containers and accessible text summaries. Reports and Investments use
the same interaction contract. Income uses the green pair, expense uses the red pair, and
investment has its own ochre pair. The recurrence donut uses purple
installments, orange fixed recurrences and neutral one-off purchases; its zero
line is neutral. HTMX swaps only the report island while preserving focus and
viewport; plain links/forms remain equivalent.

SVG paint order is part of that contract. Every interactive chart renders all
data marks and axis labels in a base `data-chart-layer="*-marks"` layer, then
renders transparent hit targets, hover/focus highlights and tooltip pills in a
final `data-chart-layer="*-interactions"` layer. Tooltips must never be nested
only beside their original mark in series order: later SVG elements would paint
over them. Tooltip content remains `pointer-events-none`, while its transparent
hit target retains the native `<title>`, keyboard focus and any chart link.

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

## Automated browser checks

`tests/e2e/design-system.spec.js` checks translated landing copy, local HTMX,
CSV downloads, responsive navigation, dashboard month states, conditional loyalty
fields, monetary-yield forms, salary-sandbox calculations and help, and report
navigation. These checks cover
browser behavior that template assertions cannot prove.

Run `npm run test:e2e` for an isolated application and temporary database. CI
uses the same executor and retains configured browser failure artifacts. See
[CONTRIBUTING.md](../CONTRIBUTING.md#browser-tests) for setup, argument forwarding,
logs, and the advanced manually managed path.

`tests/preview/preview.spec.js` validates the static GitHub Pages tour in both
languages, including the committed image dimensions, theme persistence,
accessible screenshot dialog and mobile layout. Run `npm run test:preview` for
that isolated site. `npm run preview:capture` regenerates its screenshots using
only disposable synthetic records in a guarded temporary database. The capture
and test configuration is documented in
[`../.github/preview/README.md`](../.github/preview/README.md).
