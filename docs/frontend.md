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
HTMX when they target a documented page or island update. Body swaps for the
same pathname preserve viewport and focus; navigation to another pathname moves
focus to the new `h1`. Report and investment chart islands keep their existing
focus and scroll restoration. The
investment movement island updates filters and pagination independently, then
returns to the beginning of the movement section instead of the top of the page;
plain GET links and the section anchor provide the same no-JavaScript fallback.

## Preserve the user's location

Every new or changed interaction that updates the current page must preserve the
user's viewport and interaction context. This includes type/category cards,
filters, sorting, pagination, refreshes, and inline edits or validation feedback.
Do not send the user to the page heading or scroll to the top after an update.
Treat navigation to another page and explicit links to a named section as
navigation, rather than as an in-place update.

- Reuse `static/js/navigation.js`: a successful HTMX body swap whose final URL
  has the same origin and pathname restores the scroll coordinates captured
  immediately before the swap. Query-string changes do not start a new page.
  The handler overrides inherited `show:window:top` with `show:none` and restores
  the surviving focused control with `focus({preventScroll: true})`.
- Give controls stable, unique IDs so keyboard focus can survive replacement.
  Do not add an unconditional `h1.focus()`, `scrollTo(0, 0)`, full-page reload or
  `show:top` to an update flow. Reuse the existing island restoration for partial
  updates; explicit section-navigation links may retain their named destination.
- Preserve URL/history and server-rendered GET/POST fallbacks. Native navigation
  without JavaScript remains usable; use meaningful section anchors where
  appropriate rather than relying on scripts for access to results.
- If filtering shortens the document, the browser may clamp the saved offset to
  the new maximum scroll position. This is the only automatic position adjustment
  expected for an ordinary update; do not jump to the heading as a fallback.
- Browser acceptance must begin at a nonzero scroll position, trigger the real
  interaction, wait for the swap to settle, and check scroll position and keyboard
  focus. Cover desktop/mobile and both populated and empty results. Also confirm
  that deliberate navigation to another page still opens that destination normally.

## Visual language

The interface follows the Tuxedo Finance design language documented in
`design-system.html`: cream and forest light foundations, neutral black and
graphite dark foundations, caramel actions, distinct semantic colors, rounded surfaces and Inter 400–700
throughout. Light cards use white surfaces and soft shadows; dark cards use flat
graphite surfaces over the near-black page background. Body copy starts at
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
Secondary text uses forest/70 in light mode and neutral night-muted in dark mode.

## Dark foundation tokens

The light palette remains unchanged. Dark foundations use `night` (#101010),
`night-surface` (#1B1B1B), and `night-raised` (#262626) for page, panel, and
hover/elevated surfaces. Use `night-muted` (#B8B8B8) for secondary text and
`night-line` (#808080) for form-control boundaries; decorative dividers may use
cream/15. Main text stays cream and financial semantic colors retain their
existing meaning. Do not redefine forest tokens to change the dark theme.

Apply dark variants to structural backgrounds, including otherwise always-dark
footers, mobile menus, and salary results. Native controls inherit dark
`color-scheme`; keyboard focus uses a visible caramel-light outline. Field
errors retain their semantic styling. Theme initialization and persistence are
shared across full navigation and HTMX swaps.

The public homepage uses factual copy, six separated feature rows, and the full
horizontal cat photograph in a translucent double rounded frame with a subtle
caramel glow. Its 4:3 mobile / 16:10 larger frame preserves the image's native
ratio; padded hover zoom respects reduced motion. It has no promotional feature
cards or example balances.
Functional cards remain available in authenticated screens. See
[pages](apps/pages.md) for the composition and authentication behavior.

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
forest-deep modal in light mode and near-black modal in dark mode, with the same
links and ordering as desktop. It slides in,
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

### Keyboard and choice contract

This is mandatory for **all existing, new and changed forms**, including filters,
settings and imports. Use the shared field renderer and test the interaction;
custom pickers must not be copied into individual templates. The implementation
follows the [WAI-ARIA combobox pattern](https://www.w3.org/WAI/ARIA/apg/patterns/combobox/).

| Control | Keyboard behavior |
|---|---|
| All controls | Tab/Shift+Tab move forward/back in document order with visible focus. No positive tabindex or focus jumps when branches appear. |
| Searchable record choice | Type to filter; Down/Up open results and highlight the next/previous option; Enter confirms the highlighted option. |
| Search cancellation | Escape closes; Tab continues. Both restore the committed choice and discard unconfirmed search text. Enter never submits from the search input, including zero matches. |
| Short native select | Use the browser's native keys (Space or Alt+Down to open where supported, arrows to navigate and Enter to confirm). |
| Checkbox / multiple record choice | Space toggles a focused checkbox; Tab reaches each visible checkbox. Filtering preserves selected records. |
| Advanced options | Focus the native summary and press Enter or Space; Tab then visits its fields. |
| Save / other buttons | Enter or Space activates the focused button. |

Single-choice search uses manual confirmation, including when there is only one
match. Focus remains on the search input; `aria-activedescendant`,
`aria-selected` and the visible active highlight move together. Arrow navigation
stops at the ends. Home/End and text-editing shortcuts retain native editing
behavior. Mouse/touch selection and the explicitly labeled clear button perform
the same committed change.

When a user focuses, filters or opens a searchable choice, scroll only as far as
needed to show the input and results below the sticky header. Keep focus on the
input. Size the results to the available visual viewport, including after a
mobile keyboard or window resize, and keep long lists internally scrollable.
Arrow navigation keeps the active option visible inside that list; once the
picker fits, it must not keep moving the page. Use immediate scrolling so keyboard
input does not race an animation, including with reduced motion enabled.
Initialization, background refreshes and merely revealing a conditional branch
must not scroll the page. This targeted visibility adjustment applies when the
user reaches the picker and does not change the HTMX location-preservation rule.

All Django `ModelChoiceField` and `ModelMultipleChoiceField` controls rendered by
`partials/form_field.html` receive `data-search-select` through the `form_control`
template tag. This covers categories, parent categories, banks, accounts, cards,
assets, investment products, programs and invoices. Handwritten record filters
must also carry that attribute and a stable unique ID. Short enumeration choices
remain native selects. Disabled fields remain native and disabled.

`static/js/forms.js` progressively enhances these controls, using the original
scoped options and preserving their names, values, metadata and `change` events.
It reads translated text from `partials/form_ui_strings.html`. Initialization is
idempotent on DOMContentLoaded and HTMX load. Domain handlers may update native
values/options; the shared refresh runs after their change handlers. Call
`TuxedoForms.refresh(form)` after changes outside a change event. User text is
inserted with textContent, never interpreted as HTML. No remote search or new
frontend dependency is involved. Entry forms use `novalidate` so hidden native
selects cannot intercept error recovery; Django renders the validation errors.

### Conditional fields and recovery

- New choices that control branches begin empty; conditional checkboxes begin
  unchecked. Preserve submitted values, existing records and validated shortcut
  context. Model/storage defaults need not change to enforce the creation UI.
- Transaction categories wait for income/expense; a credit channel reveals the
  card selector, and a confirmed card reveals installment/bill details. Recurrence
  reveals its end date only after the checkbox is selected.
- Investment values and funding wait for an asset and operation type. Monetary
  yield requires an explicit input-mode choice. Opening balances wait for the
  valuation mode; their product appears when an opening position is supplied.
- Points purchases reveal payment amounts after a funding source is selected.
  Redemption IOF sources appear only for a positive IOF amount. Sandbox CLT and
  transport-voucher details require their respective checkboxes.
- Use `TuxedoForms.setHidden(group, inactive, preserveErrors)` for domain-specific
  branches. Simple dependencies may use `data-form-when="controller-id"` plus
  `data-form-value="checked|unchecked|positive|literal-value"`; these clear their
  inactive controls after a deliberate controller change. `data-inactive-value`
  can specify a domain-required reset value instead of an empty string.
- Every directly toggled group, including parents, must expose its own
  `data-has-errors`. Initial rendering keeps errored branches visible and opens
  advanced sections containing errors. A deliberate switch clears incompatible
  values and dismisses the abandoned branch's old errors; it must not erase
  unrelated errors or unmodified values during initialization.
- Keep dependent fields in normal DOM order and use hidden for inactive groups.
  Revealing a group never steals focus; the next Tab reaches its first control.
- Native controls remain rendered and usable without JavaScript. Do not render
  inactive branches hidden on the server. The server remains authoritative for
  ownership, compatibility and accounting validation.

Form changes require keyboard browser tests for confirmation/cancellation,
conditional transitions, invalid POST recovery, editing and the no-JavaScript
path. Start viewport tests with the picker near the bottom; check the input,
results and active option in desktop and short mobile viewports. Use the isolated
E2E executor; inspect light/dark focus and active-state contrast. The contributor
and agent instructions make this a review requirement,
with regression tests included in the existing CI browser suite.

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

The Reports summary uses three cards: live bank cash, the identified anchor
month's inflows minus outflows, and bank-balance change across the full chart
window. Monthly result excludes the opening balance and includes recorded
investment deposits/withdrawals separately from consumer income/expense. The
window-wide change keeps its existing calculation and missing-rate warning.
`stat_card.html` accepts a period `caption` and shared question-mark help through
`help_id` plus `help_text` or a trusted `help_template`. The full-window explanation follows HTMX changes
to the displayed dates. Reports no longer show a best-month summary card.

### Question-mark help

This contract is mandatory for every new or changed **?** help icon. Reuse
`partials/help_popover.html`, `static/js/help-popovers.js` and the `.help-*`
components in `assets/css/tailwind.css`. Reports and Sandbox share this behavior;
do not add independent click-to-pin tooltips or use a native title as the only help.

| Interaction | Required behavior |
|---|---|
| Mouse hover | Open without clicking. Keep the help visible when moving from the icon into its text. Close after leaving both, with a 120 ms crossing allowance. |
| Mouse click | Never pin help. Clicking outside dismisses it immediately. Only one help box may be open. |
| Keyboard | Tab focus opens help; Enter/Space can reopen it. Escape dismisses without moving focus; Tab away closes it. Pointer clicks must not leave a focus-driven tooltip stuck open. |
| Touch | Tap toggles help. Another tap, an outside tap or another help icon dismisses the previous box. |
| Navigation | HTMX swaps/history close floating help and initialize replacement controls once. No duplicate fallback controls or event handlers. |
| No JavaScript | A native details/summary fallback exposes the same explanation by keyboard or touch. |

Help is rendered above cards/charts in a floating container attached to the body,
with a preferred width of **352 px**, a **12 px** viewport gutter and an **8 px**
gap from the icon. Its width must never inherit the icon or label width. Reposition
above the icon when needed, constrain height in short viewports, and allow internal
scrolling. Reposition on resize/scroll without moving the page or stealing focus.

Use 14 px text, 24 px line height, normal capitalization, left alignment and 16 px
padding. Give the explanation a short title and separated paragraphs; put formulas
in their own lightly shaded block. Keep paragraphs short and fully translated.
Use the shared light/dark surfaces, borders and visible focus. Do not put links,
form fields or other interactive controls inside a tooltip.

Pass a stable, unique `help_id`, a translated `help_label`, and either plain
`help_text` or a repository-owned `help_template`. The latter may use
`.help-paragraph` and `.help-formula` spans for structured copy. Template paths
must be authored literals, never user input. Both the tooltip and no-JavaScript
fallback render the same content; ordinary text remains escaped. The trigger's
accessible name explains its subject, and `aria-describedby` references the
`role="tooltip"` content.

```django
{% include 'partials/help_popover.html' with help_id='budget-help' help_label=budget_label help_text=budget_help %}
```

Review changes with actual pointer, keyboard and touch tests: enter/leave the
icon and content, outside click, click then leave, Escape/Tab, a second icon,
HTMX/history and the no-JavaScript fallback. Inspect English/Portuguese copy in
both themes at desktop and mobile widths; assert box width/viewport bounds so
an extremely narrow column cannot pass as readable help.

Charts remain inline server-rendered SVG/CSS with native `<title>` fallbacks,
theme-aware tooltip pills on mouse hover and keyboard focus, responsive
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
