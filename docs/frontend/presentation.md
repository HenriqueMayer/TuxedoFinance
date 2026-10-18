# Frontend presentation and shared components

[Frontend index](../frontend.md) · [Interface map](../interface-map.md)

## Editorial application adoption

The validated catalogue direction applies across the public homepage,
authentication, five workspaces and their secondary editors. The
[interface map](../interface-map.md) records every route family, shared control and
domain exception. Django templates, owned records, financial validation and
existing URLs continue to define the application; styling does not enable
features still behind a review gate.

`assets/css/interface.css` supplies the product-wide presentation under
`body.tuxedo-ui`: neutral surfaces with 14px corners, thin ledger dividers,
44px actions with balanced 12px corners, compact fields with 8px corners and
readable focus/error states in both themes. `workspace-form`,
`workspace-form-page` and `form-actions` organize secondary editors without
changing their controls or submission behavior. `form_control` adds `entry-input`
to ordinary widgets while retaining their original types, attributes, precision,
names and IDs. Hidden controls, native radio/checkbox groups, files and color
widgets keep their separate presentation. Handwritten controls use the same
shared classes. Do not copy a competing picker or add per-page pill actions.
Investment and planning editors additionally use `finance-entry-page` and
`finance-entry-form` for a shared sheet up to 56rem. `finance-entry-grid` groups
related short fields in two columns from 640px and stacks them on smaller
screens; `finance-entry-wide` keeps descriptions and record choices readable.
`finance-entry-section` separates funding, initial values and reservations with
a thin divider. Preserve DOM reading order, conditional owners and errors;
layout must never reveal a hidden group or change a submitted identifier.
Long user-entered names must wrap within headings and flex/grid children without
displacing their adjacent action. Ordinary record-choice results wrap the full
label inside the list and retain 44px targets; the committed search input stays
single-line; payment miniatures retain their separate compact presentation.
Small-screen row menus must fit the viewport, including when a
long row name moves its actions onto another line.
Complete registrations use named `finance-entry-group` fieldsets for identity,
valuation/opening and funding. Their native legends replace extra nested cards;
optional details remain deliberate disclosures, open when errors need recovery.
Planning tools reuse the same entry width while comparison tables keep the full
workspace width and scroll within labelled, keyboard-accessible regions.
Single boolean fields use the existing `entry-checkbox-choice` row automatically:
the native checkbox sits beside its label and contextual help, with a 44px row
and unchanged checked values, keyboard behavior and rendered error recovery.
Secondary editor Cancel links use `quiet-action`; destructive confirmations
group their explanation and original POST actions in one shared surface panel.
Feedback that quotes a user-entered record name wraps inside its notice panel,
including names without spaces; it must not widen the document on a phone.
Keep the measure in confirmation summaries appropriate to the record: monetary
operations show money, unit operations retain their quantity precision, and
loyalty entries use translated directions with their program's unit name.

The application shell uses the same five direct destinations on its desktop
sidebar and mobile bottom navigation: Home, Transactions, Accounts, Investments
and Plan. Icons, labels, quieter surfaces and restrained active/hover feedback
follow the Workspace specimen; decorative destination numbers are omitted.
Section tabs retain each workspace's
secondary destinations. Deliberate user menus, native links, shared Back/Forward,
HTMX focus/scroll recovery and private-history reauthorization keep their
existing contracts. Bank-colored markers continue to identify institutions;
navigation styling never substitutes color for a destination or financial state.

The transaction sheet follows the catalogue's compact reading order and uniform
controls while retaining category splits, recurrence, installments, invoice
selection, account/card metadata, contextual Save/Cancel and rendered Django
errors. Only `transaction_type` and `payment_channel` use the native
`SegmentedChoice` radio widget. Their fieldsets have real legends and individual
option labels; visual selection and focus do not resize their targets. New
groups remain unselected unless an owned shortcut explicitly supplies context.
Bound invalid POSTs and edited records retain their choices. Native form POSTs
remain complete without JavaScript.

With JavaScript, Add category sits immediately after its allocation rows and
before payment controls in both visual and Tab order. It is a non-submit action.
The server HTML keeps its native Add fallback after Save, so Enter in an ordinary
field still submits Save when JavaScript is unavailable.

The shared payment board presents owned account and PIX options with their
respective icons, the bank's color marker, account name, institution and currency.
Card options use their saved colors/gradient, nickname and account context. A
compact 44px search field accompanies the miniatures. Essential text remains on
a neutral surface, independently of custom colors, using the shared contrast
protection described under [card appearance](forms.md#card-appearance).
`assets/css/payment-choices.css` owns this shared artwork and board presentation
across transaction and banking editors, including multiple-card choices.

The [persistent payment-choice contract](forms.md#persistent-payment-choices)
owns opt-in, keyboard and selection behavior, channel eligibility, native
submission and metadata/ownership rules. Keep those rules in Forms rather than
redefining them through a presentation change.

## Visual language

The canonical catalogue and application load the same compiled stylesheet.
Tailwind scans templates, app form classes and the catalogue; rebuild CSS after
changes instead of copying tokens or relying on a JavaScript CSS CDN.

The interface follows the Tuxedo Finance design language documented in
`design-system.html`: cream and forest light foundations, neutral black and
graphite dark foundations, caramel actions, distinct semantic colors, rounded surfaces and Inter 400–700
throughout. Workspaces group related information in restrained surface cards,
metric cards, semantic tables and ruled sections. Avoid nested cards and use
spacing to distinguish the contents of one group. Page titles use 28px on mobile
and 32px on desktop; section titles use 18px and 20px. Body copy starts at
16/24px, labels and supporting copy at 14/20px, and compact table labels never
fall below 12px. Bound chart heights preserve readable proportions on wide screens.

`assets/css/reporting.css` owns the Home/report refinements. Dense time-series
charts retain their readable canvas width inside named, focusable horizontal
scroll regions, with a short phone hint; do not compress away months or change
their datasets to fit the viewport. Category marks have at least 44px targets,
and full record names and selected-period summaries wrap inside their panels.
Period presets keep the same 44px geometry in active and linked states, with
`aria-current` on the selected preset. These are presentation rules; chart
cutoffs, aggregation and Decimal amounts remain in the existing services.

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

The navigation brand combines the local Tuxedo mark with a compact, ordinary-case
wordmark. It always
links to Home for authenticated users and the public landing page for anonymous visitors. Primary
actions use balanced 12px corners and solid caramel with forest-deep text; `caramel-ink` carries
brand links over light surfaces. Shared outline and quiet actions use subtle
neutral hover surfaces. Titles, labels, controls and tabular monetary figures all use Inter.
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

The public homepage pairs factual copy and access links with the Paper Layers
bow tie and its five-workspace index. Seven separated feature descriptions cover
the available product areas. The illustration supports pointer, keyboard and
touch, respects reduced motion, and retains native links without JavaScript.
The page shows no example balances.
Authenticated workspaces follow the shared composition below. See
[pages](../apps/pages.md) for the composition and authentication behavior.

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

Conditional form controllers that use Django-rendered data stay in their owning
template directory: `transactions/_form_script.html`,
`investments/_form_script.html`, `investments/_setup_form_script.html` and
`banking/_loyalty_form_script.html`. Their parent editors include them in the
same position as the rendered script; shared browser engines remain under
`static/js/`. This separation changes source ownership without changing script
execution order or turning translated, server-provided data into external code.

Money rendering follows the authenticated user's base reporting currency.
Historical transfer and investment totals identify their persisted FX snapshot;
other current valuations show their valuation date and rate source.

The shared footer uses a thin theme-aware divider, small text attribution and
the retained copyright/author link. It has no logo image or contrasting brand
banner; light and dark pages use the same quiet layout. It remains in normal
flow, with the shell reserving space for fixed mobile navigation.

## Multicurrency display

The UI uses the authenticated user's `UserPreference.base_currency`, selected
from Settings. Changing it updates consolidated presentation only; native
amounts remain unchanged. Transfer/investment historical snapshots and current
valuations are visibly distinct, and missing rates are shown explicitly as
incomplete.

Native decimal controls retain dot-decimal submission. Only explicitly opted-in
[transaction cents entry](forms.md#transaction-amount-entry) uses a formatted text field
with canonical decimal submission; quantities, rates and empty overrides keep
their own native precision. Display localization follows each currency's
formatting metadata; SVG coordinates and CSS percentages remain unlocalized.

UI language does not choose currency formatting. `core/formats/en/` and
`core/formats/pt_BR/` both delegate separators to the selected currency, so a
language switch cannot turn a correctly formatted amount into a mixed
symbol/separator representation.

## Responsiveness and accessibility

All pages remain mobile-first. Wide ledgers, invoice item tables and charts use
internal horizontal scrolling rather than forcing body overflow. Bank/account
hierarchies retain grouped rows on small screens, with internal table scrolling
when columns cannot fit legibly. Labels, status text,
focus rings, keyboard navigation and confirmation screens remain available
without relying on hover, color or JavaScript.

## Shared workspace components

Investment, Planning and Sandbox main regions receive `.finance-workspace`.
This scope adopts the approved Accounts density for headings, surfaces and
actions without changing shared field/choice geometry or reducing 44px touch
targets. Holdings and category budgets use one divided surface with aligned
desktop columns and a stacked phone layout. Keep values, evidence and actions
distinct; never sum category limits into available cash or turn acquisition cost
into a market quote. Goal cards and grouped tool links reuse these same tokens.
Value/calculation disclosures retain stable IDs so live refresh preserves the
reader's explicit open/closed state. Critical missing-data warnings stay visible.

Use `surface-panel`, `metric-panel`, `label-with-help`, `workspace-header`, `section-nav`, `action-link`, `action-primary`,
`secondary-actions`, `data-table`, and `subtle-copy` from the compiled stylesheet.
Group banks, charts, input stages and results in distinct surface cards. Use
compact metric cards for comparable summaries and divided rows inside each
group. Avoid nested bank/product/asset cards. Explanatory copy belongs in the
shared question-mark help beside its heading or label; errors, missing FX,
incomplete values and decisions requiring user action remain visible.
`form_field.html` renders ordinary field help beside the label automatically;
`field_help_text` and `field_help_template` supply contextual overrides without
duplicating the help below the field. Keep the existing palette, Inter typography, shared help, fields,
searchable choices, and accessible focus tokens. Record a reusable composition
in `design-system.html` before introducing a competing per-page pattern.

Complete calendar dates use `core.dates.configure_date_fields` and
`partials/preferred_date_field.html`, dispatched by the normal form-field
partial. The shared script initializes after full loads and HTMX swaps without
moving focus or rewriting every keystroke. The user's DMY/MDY setting controls
visible date fields and complete dates throughout the application. Native
calendar helpers, storage, existing CSV formats, and URL parameters use ISO;
month-only labels remain localized month/year labels. An invalid bound value is
retained for recovery. Stored calendar dates are not shifted through browser
time zones; the shared dialog uses UTC components only for day/month
arithmetic.

HTMX regions with `data-preserve-view` use the common navigation handler to
restore focus and scroll. Account participation updates also replace the
availability summary out of band, so the row and aggregate remain consistent.

## Bank identity markers

Bank colors use a validated six-digit hex value, a native color field and optional
preset swatches. Existing banks receive the neutral caramel marker. The list uses
a slim corner marker; the marker next to the detail title links to a color-only
edit form. Native submissions work without JavaScript and updates enforce bank
ownership. Color does not carry financial meaning.
