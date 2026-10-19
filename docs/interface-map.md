# Application interface map

This inventory maps the application routes to their screens, controls and shared
components. It is the checklist for applying the approved
[design catalogue](design-system.html) and the current transaction, card and
category interactions consistently. Detailed interaction rules remain in the
[frontend guide](frontend.md); financial rules remain in the
[data model](data-model.md) and [per-app references](README.md#per-app-reference).

The inventory was checked against the URL configurations, owning forms/views,
shared partials and application templates on 2026-10-17. Related create, edit and
delete routes are grouped below; `<id>` denotes an owned record identifier.
Abbreviated paths in a row retain that row's application prefix.

## Navigation and access

The desktop sidebar and mobile dock have the same five destinations. Secondary
screens belong to their workspace; an editor retains its workspace context.

| Destination | Entry route | Secondary destinations |
|---|---|---|
| Home | `/dashboard/` | Dashboard and Reports. Net worth remains under review. |
| Transactions | `/transactions/` | Transactions and Categories; existing import provenance remains readable. New statement imports remain under review. |
| Accounts | `/banking/` | Accounts, Invoices and Exchange rates. Banks, cards, cash positions and loyalty belong to this workspace. |
| Investments | `/investments/` | My investments, History, and deliberate More options for Analyses, Observed prices and Full configuration. |
| Plan | `/planning/` | This month, Goals and Tools; salary/yield scenarios, saved drafts and signals belong to Tools. |

Settings, language, theme, project links and POST logout remain in account or
utility controls. Primary navigation has no hover submenus. Option menus open
deliberately; question-mark help keeps its separate hover/focus behavior.
The authenticated assistant is a utility panel/native destination, not a sixth
primary workspace. Its local foundation has no connected model or financial
execution. Assistant settings owns default-disabled account-authorization
preparation; account linking never replaces Django login or enables inference.
See the [assistant guide](apps/assistant.md).

## Screens and route families

### Public pages and authentication

| Routes | Interface and actions | Preserved boundaries |
|---|---|---|
| `/` | Product identity, factual description, Paper Layers illustration/workspace map, feature rows, login/signup or authenticated workspace action. | No financial queries on the public page. Signup links follow `ALLOW_SIGNUPS`. Illustration supports pointer, keyboard and touch, with reduced motion. |
| `/accounts/login/` | Username/password, Sign in, conditional signup link, credential and field errors, explicit local destination. | Native authentication autocomplete and no-JavaScript POST remain available. |
| `/accounts/signup/` | Username/email/password confirmation, registration errors, Sign up or closed-registration state, login link. | Signup policy and server validation; no demo financial records are inserted by registration. |
| `/accounts/settings/` | Consolidation currency and complete-date order, contextual help, Save/Cancel. | Preferences change presentation; native record currencies and calendar dates retain their meaning. |
| `/accounts/logout/`, `/i18n/setlang/` | Explicit logout and locale submissions. | POST actions, existing session/security behavior and validated destinations. |

### Assistant utility

| Routes | Interface and actions | Preserved boundaries |
|---|---|---|
| `/assistant/`, `/assistant/<uuid>/` | Local conversation list/detail, explicit New conversation/Delete, compact current-page context link and unavailable provider/composer; fixed desktop overlay, mobile sheet and native full-page fallback. | Opening/closing preserves workspace/filter geometry. Stationary controls contain gentle artwork motion with reduced-motion support. Owner-scoped UUIDs, no-store responses, shared keyboard/focus/mobile clearance and no fake model reply. Outside `main`; whole-body HTMX navigation reconstructs the panel and refetches its owned conversation. |
| `/assistant/conversations/new/`, `/assistant/<uuid>/delete/` | Explicit CSRF-protected local POSTs. | Create/delete owned conversation history only; no financial write. |
| `/assistant/<uuid>/messages/` | Unavailable-provider recovery for a stale/direct POST. | HTTP 503 without saving a fake exchange; no external request or paid fallback. |
| `/assistant/context/` | Timestamped/cutoff/currency-aware structured context with metrics, warnings and owned source links. | Signed expiring user-bound origin, allowlisted route/query, ownership rechecks, read-only collection and no DOM/unsent-form capture. |
| `/assistant/connections/` | Owned ChatGPT account settings, local selected/status metadata, pending confirmation and explicit connection actions; empty/disconnected state by default. | No external request or vault initialization on GET; never seeds a fictitious linked account. Shared native forms and readable long identity text; provider/composer stays unavailable. |
| `/assistant/connections/start/`, `connections/<uuid>/authorize/` | Native CSRF POST for Continue with ChatGPT or Sign in again. | Real authorization disabled by default; explicit future opt-in and deliberate user action required. Leaves HTMX before the external handoff, without replacing Django login. |
| `/assistant/connections/callback/`, `connections/callback/result/` | One-time loopback callback and generic result directing the owner to the original settings tab. | No immediate account attachment, callback-host session assumption, token/account rendering or reusable query. No-store/no-referrer; final confirmation belongs to the original authenticated session. |
| `/assistant/connections/attempts/<uuid>/finish/`, `.../cancel/`, `connections/<uuid>/activate/`, `.../disconnect/` | Explicit native CSRF POSTs for reviewed account linking, attempt cancellation, local selection and deliberate disconnect confirmation. | Owner/session checks; no token fields in forms, browser storage or logs. Identity-only/reconnect/revocation-failure recovery stays explicit; financial data and conversations remain. |

### Home and reporting

| Routes | Interface and actions | Filters and interaction contracts |
|---|---|---|
| `/dashboard/` | New transaction; planning availability; current account balances with bank markers; monthly performance, expense categories, outstanding invoices and six-month outlook; FX warnings and contextual help. | Month arrows/reset affect their owning period. Account shortcuts reveal the exact bank row. Outstanding invoices include overdue obligations independently of that month; All invoices opens the complete card overview. Wide tables scroll locally. |
| `/dashboard/reports/` | Current balance, monthly result, twelve-month change; balance/cash-flow, instrument, installment/recurrence and category charts; legends, notices and source details. | Independent window/month/current/Last 12 months controls preserve the other query parameters. The legacy ALL value covers the current month plus eleven prior months. HTMX GET replaces the owning charts and updates history without a POST departure warning. |
| `/dashboard/chart-details/` | Composition amounts, source links and generated-operation context. | Signed/user-owned scope, discreet source disclosures, no arbitrary editor for an aggregate. Home/Reports source links retain query and owning-chart anchor for editor Save/Cancel. Shared chart composition behavior applies. |
| `/dashboard/wealth/` | Dated assets/debt/net-worth metrics, completeness notices and monthly series. | **Paused:** redirects through the review gate; remains absent from product navigation. See [review boundaries](#review-and-framework-boundaries). |

### Transactions and categories

| Routes | Interface and actions | Filters and conditional controls |
|---|---|---|
| `/transactions/` | Source-aware ledger rows, counts, New/Edit/Split/Delete, generated-record links, pagination and deliberate export menu. | Text search includes categories; month and type; compact More filters row for transaction date, recurrence and order. Legacy exact-category URLs show clearable context. Stable Clear/count slots, GET fallback, keyboard focus and location remain. |
| `/transactions/export/` | Raw or spreadsheet-safe CSV and selected-month export. | Read-only GET; retain CSV formula-neutralization choices and billed-month semantics. |
| `/transactions/create/`, `/<id>/edit/` | Type; description/amount/date/category; optional category split; payment channel; persistent account/PIX/debit/credit miniatures and compact shared filter; Save/Cancel. | Blur does not dismiss instruments. Selection stays explicit. Automatic split rows share the remainder around edited amounts; server errors, recurrence, installments, invoice context and validated return filters remain. |
| `/transactions/<id>/split/` | Automatic/fixed category amounts, Remove category, Add category, Save/Clear/Cancel. | Integer-cent distribution, exact installment conservation, original formset identifiers and server validation; labelled native DELETE/Add fallback without JavaScript. |
| `/transactions/<id>/delete/` | Source summary, destructive confirmation and Cancel. | POST-only financial deletion and generated-operation restrictions. |
| `/categories/` | Search, hierarchy, native expand/collapse, row menus, counts, New category and deliberate import/export/delete-all options. | Level and Type are always-visible native segmented radios. They combine with text search and stable Clear, preserving GET values and history. |
| `/categories/create/`, `/<id>/edit/` | Name/type/parent, Save/Cancel and errors. | Shared searchable parent, ownership, type compatibility and cycle validation. |
| `/categories/<id>/delete/`, `/delete-all/` | Single/all-category confirmation, Delete/Cancel. | Protected usage and explicit POST; no cascade or hierarchy rule change. |
| `/categories/import/`, `/export/` | Local category CSV upload, structural feedback and raw/safe export. | This active category utility is separate from paused statement ingestion. Byte/row/field limits, parser errors and atomic validation remain. |

### Accounts, banking instruments and invoices

| Routes | Interface and actions | Filters and conditional controls |
|---|---|---|
| `/banking/`, `/<id>/` | Always-visible balance breakdown; bank grid opens one full-width internal workspace with a labelled Minimize action. Accounts/reserves, cash pots, card miniatures, loyalty, activity and inline reward editing remain. | Existing native URLs and Back/Forward identify the selected panel. Minimize restores the grid's location/focus so another bank can be opened, including without JavaScript. Whole-workspace GET establishes its baseline; inner POSTs preserve errors and edited-state protection. |
| `/banking/create/`, `/<id>/edit/`, `/<id>/color/`, `/<id>/delete/` | Bank name/color/palette, Save/Cancel and protected deletion. | Bank identity color is decorative, independent of financial status. |
| `/banking/accounts/create/`, `accounts/<id>/edit/`, `accounts/<id>/delete/` | Bank/name/currency, opening balance/date, reserve and PIX settings. | Shared owned-bank selector, opening/history checks and native fallback. |
| `/banking/accounts/<id>/planning/`, `cash-positions/<product>/<asset>/planning/` | Include/exclude balance and reservation controls. | Explicit POST, existing cash/reserve accounting and availability guards. |
| `/banking/debit-cards/...`, `/banking/credit-cards/...` create/edit/delete | Account and nickname, own color presets/custom colors, optional gradient, circular angle control and live miniature; credit closing/due dates and settlement settings. | Native fallback for angle and colors; no autosave. Keep account ownership, invoice-cycle/history checks and color/angle validation. |
| `/banking/transfers/create/` | Source/destination, amounts, date/notes, Save/Cancel. | Same-currency conservation, account ownership and opening-date validation. |
| `/banking/loyalty/...` create/edit/delete | Program/name/bank/unit and a searchable, illustrated multiple-card board with native checkboxes. | Owned compatible records; filtering retains selected cards; no new point valuation rule. |
| `/banking/loyalty-entries/...` create/edit/delete | Program, kind/direction/amount/date/notes; illustrated invoice-award or purchase funding/account/card/cash branches. | New conditional choices start empty; deliberate transitions clear incompatible values; bound errors and financial postings survive. |
| `/banking/rewards/redeem/`, `rewards/<id>/edit/` | Program/points, target account, cash/IOF/fees/date/notes. | Existing generated-operation editing, posting and contextual return rules. |
| `/banking/invoices/`, `credit-cards/<id>/invoices/` | Card/bank/account/currency identity, invoice rows/status/counts, pagination and own-color miniatures. | Search and compact exposed month/bank/status criteria, stable Clear and live GET fallback. Automatic and confirmed modes keep their distinct meaning. |
| `/banking/invoices/<id>/` | Due/status/total, confirmed/remaining payments, overpayment notices, card settings, payment/source links, account/amount/date/notes payment entry. | Explicit record of a payment already made; the application does not send money. Ownership and server settlement checks remain. |
| `/banking/invoice-payments/<id>/edit/`, `invoice-payments/<id>/delete/` | Payment editing or destructive reversal confirmation. | Original posting/reversal, contextual origin and native POST. |
| `/banking/exchange-rates/` and create/edit/delete | Local dated rates, visible source-unit/target-value explanation, compact exposed currency/date criteria, Clear, pagination and row options. | Historical FX remains user-recorded; Decimal precision and source/destination/date validation remain. |

### Investments

| Routes | Interface and actions | Filters and conditional controls |
|---|---|---|
| `/investments/` | Position/value summary, holding rows with saved bank markers, contextual history, Add investment and holding actions. | Search and purpose scope (all/investments/remunerated cash), stable Clear and live GET results. Scope also updates the History destination. |
| `/investments/positions/<product>/<asset>/`, `positions/<product>/<asset>/update/` | Cost, dated price, results, operations/configuration; Contribute, Redeem, Record yield and unit-price actions. | Mode-specific actions and archive locks. Dated prices affect valuation, not quantity or bank cash. |
| `/investments/operations/` | Searchable operation history, source/funding information, Edit/Delete and pagination. | Purpose/type/bank/product/asset/currency/class/date criteria; shared record search and live consultation. |
| `/investments/add/` | Guided existing/new institution, name, valuation mode, currency/purpose/planning inclusion, opening position and optional code/class. | Monetary versus units branches; opening date reveal; explicit initial choices and nested errors. Opening holdings do not imply a bank debit. |
| `/investments/create/`, `/<id>/edit/`, `/<id>/delete/`, `/yield-preview/` | Product/asset/type/date, monetary amount/yield/final balance or units/unit price; funding/destination/cash/points; advanced fees/reason/notes; optional FX capture; preview and confirmation. | Native yield-mode segments, shared record search, mode-specific fields, deliberate stale-value clearing and nested error recovery. HTMX preview retains the original submitted context. |
| `/investments/settings/`, `/products/...`, `/assets/...` | Compact institution-marked product/asset catalogues; grouped complete registration for identity, purpose, valuation and opening holdings; direct Edit/Archive/Restore and deliberate secondary menus. | Historical opening protection and unavailable-new-operation guards remain; archive preserves balances/history and its stable action focus. |
| `/investments/prices/` and create/edit/delete | Dated unit price/source table, always-available shared asset filter, observation editor, pagination and confirmation. | Invalid/foreign asset criteria return errors and no rows. Exact precision, owned asset and local source; no external quote feed. |
| `/investments/charts/` | Scope-aligned current valuation summary/warnings, total/flow chart windows, previous/next and composition controls. | Summary and charts refresh together. Position source history stops at the plotted month's end; source-editor returns retain chart scope/windows/anchor. Financial calculations remain unchanged. |

### Planning and scenarios

| Routes | Interface and actions | Filters and conditional controls |
|---|---|---|
| `/planning/`, `/planning/budgets/` | Month outlook, current/reserved/forecast amounts, notices, category budgets/progress/remaining, New/Edit/Remove limit, Copy previous month and explanations. | Shared named-month live GET. Copy/remove are explicit POSTs; budgets do not become additional cash reservations. |
| `/planning/budgets/create/`, `budgets/<id>/edit/`, `budgets/<id>/delete/`, `budgets/copy/` | Category/month/currency/limit editor and deliberate mutations. | Existing ownership, category validation and month/origin continuity. |
| `/planning/goals/`, `goals/<id>/` | Backed-progress summary with target/remainder/deadline, divided reserved-source rows with bank identity and shortfall/FX notices; New/Details/Edit, Add/Edit/Release reservation and Archive/Restore. | Preferred dates match the list. Source links open the exact account or cash-pot position. Search, Include archived disclosure and Clear use live GET results. Reservations remain backed by existing balances. |
| Goal create/edit/archive and reservation create/edit/delete routes | Compact grouped goal fields; optional reserve-now, then source and amount; Save/Cancel. | Shared source search and remaining-capacity labels, excluding the current reservation on edit; nested errors, deliberate incompatible-value clearing, explicit POST and original target/source currencies. |
| `/planning/tools/`, `/signals/`, `/signals/settings/`, `/signals/review/` | Tool links, explained signals with separated source/action lists, reviewed checkbox/Clear, Acknowledge/Dismiss/Reopen and grouped rule/threshold settings. | Settings, review decisions and editable source links retain the consultation origin/reviewed filter. Disabled rules keep thresholds; displayed dates do not change evidence fingerprints. Decisions do not mutate financial sources; evidence limits remain. |
| `/sandbox/` | Gross salary/month, previous/next, expense forecast; Add/Remove fixed R$/% expense; CLT inputs/tax brackets; Calculate and explicit Save draft. | Owned HTMX workspace preserves disclosures and location; dynamic rows keep native POST fallback, names and unit semantics. |
| `/sandbox/simulation/` | Initial balance/currency/month, rate period/rate/duration shortcuts, contributions/withdrawals, monthly override table, Calculate/results and Save scenario. | Rate precision, empty-versus-zero overrides, live result updates and unsaved-result protection remain. Saving is always explicit. |
| `/sandbox/drafts/`, `drafts/compare/`, `drafts/<id>/`, `drafts/<id>/duplicate/`, `drafts/<id>/delete/` | Private draft table, select up to three, compare, reopen, duplicate and delete confirmation. | Saved snapshots stay distinct by kind/currency; no cross-currency sum or automatic save. |

## Canonical component checklist

| Component | Shared implementation / presentation | Required behavior |
|---|---|---|
| Shell and sections | `base.html`, sidebar/mobile/navigation partials, `core.workspace_navigation`, `section-nav`. | Five equivalent destinations, active context, fixed-navigation clearance, native links and authorized history restoration. |
| Panels and ledger | `surface-panel`, `stat_card`, `page-title`, `section-title`, `metric-label`, `data-table`, `planning-sheet-input`. | Thin dividers, compact editorial spacing, readable status/empty/error states, local overflow instead of clipped columns. |
| Actions | `action-primary`, `action-link`, `quiet-action`, `action-danger`, `icon-action`, `form-actions`; transaction action equivalents. | Balanced content, stable geometry, visible focus, adequate touch targets, sentence-case labels and reduced-motion support. Destructive actions remain explicit. |
| Ordinary fields | `partials/form_field.html`, `field_label.html`, `form_control`, `entry-input`, `entry-checkbox-choice`, `workspace-form` / `workspace-form-page`. | Native labels/types, single booleans beside their label/help, shared errors, server validation, no-JavaScript submission, preserved identifiers and autocomplete rules. |
| Short choices | Native selects or `SegmentedChoice` / `entry-segment-options`. | Native keyboard/POST semantics. Use segments where approved, without converting long record lists into unsearchable button walls. |
| Record choices | Shared `data-search-select` enhancement, safe native option metadata and `payment-choices.css` miniatures. | Stable IDs, explicit compatible selection, keyboard search/scroll, empty conditional starts and error recovery. Payment filter blur keeps its board/query; multiple cards retain native checkboxes and selections outside the filter. Ordinary choices retain their existing dismissal. Never add an independent picker. |
| Category allocation | Shared allocation row/formset and `category-allocation.js`. | Integer-cent automatic remainder, edited amounts fixed, clear to redistribute, explicit removal, compatible new rows and recoverable server/client limits. Restore only sanitized structure and identity-scoped fields. |
| Dates and months | Preferred-date field and shared calendar engine; `partials/month_filter.html` for month consultation. | Full-date order follows preferences; canonical values remain ISO. Month-only search and reset keep their separate contract. |
| Instrument identity | Bank markers, account/PIX icons, card miniatures, card appearance and angle dial. | Names/context remain readable independently of arbitrary colors. Display identity color separately from income/expense semantics; preserve native color/angle fallback. |
| Consultation | `live-filters.js`, `consultation-bar`, `filter-disclosure`, compact banking criteria, stable Clear/count/result slots. | Debounced text, committed choices/dates, focus/caret/scroll/history preservation and native GET fallback. Category Level/Type and invoice/FX short criteria stay visible. |
| Period navigation | `period-navigation`, dashboard/report period partials, investment charts and catalogue example. | Permanent previous/next slots, visible unavailable bounds and a separate reserved reset row. Preserve original date scopes and other query parameters. |
| Edited-form departure | Shared `departure_confirm.html`, native dialog and `previous-workspace.js`. | Safe initial focus, Stay/Escape/backdrop recovery, approved original link/hash and same-document traversal. Browser-owned cross-document/reload/tab-close warnings remain native. |
| Help and menus | `help_popover.html`, native `details`, `secondary-actions`, `compact-menu`. | Help closes on icon pointer exit; menus require deliberate activation and preserve their outside/Tab/Escape dismissal rules. |
| Charts | `chart_selection.html` and owning signed datasets/details. | Existing selection, Ctrl/touch composition, focus/scroll/close protocol, ownership, generated-edit locks and source precision. |
| Feedback | Shared messages, field/nonfield errors, warnings, badges and empty states. | English/PT copy, semantic color plus text, live announcements only where appropriate, no misleading success or inferred financial state. |

## Numerical and domain exceptions

Visual consistency does not mean identical parsing or forced two-decimal input:

- Only fields explicitly opted into transaction-style amount entry fill cents
  from the right. Pasting a formatted amount, native fallback and server Decimal
  validation retain their existing meaning.
- Quantities, unit prices, rates, FX and loyalty values retain their configured
  precision. A sandbox fixed expense may be money **or** a salary percentage.
- An empty monthly override means “use the default”; zero explicitly replaces it.
- Dates are calendar dates, not timestamps. Complete-date preference, ISO
  submission and month-only consultation remain distinct.
- Category splits conserve both the total and category cents across installments.
  Transfer conservation, fee classification, settlement modes, opening dates,
  reserve backing and chart cutoffs are domain rules, not styling decisions.
- Decorative bank/card colors never replace financial semantic colors. Generated
  records and aggregate chart sources retain their existing editing restrictions.

## Review and framework boundaries

`core.settings.REVIEWED_FEATURES` is currently empty. `core.features.review_gate`
protects both GET and POST entry into paused features:

- Net worth (`/dashboard/wealth/`) redirects to Home and remains absent from tabs.
- Statement upload/mapping/review/confirmation/undo (`/imports/` and the
  corresponding `/<id>/...` routes) remain paused and redirect to Transactions.
  Their retained templates describe explicit CSV/OFX upload, column mapping,
  per-row decisions/matches, confirmation, reconciliation and guarded undo; shared
  styling is not authorization to enable that workflow.
- `/imports/history/` and completed `/imports/<id>/` remain authenticated,
  read-only provenance. Search/pagination, hashes, saved decisions, source links
  and reconciliation remain accessible; no undo action is exposed while paused.
- The unavailable investment simulation notice remains explanatory, without
  enabling a separate operation. Existing Sandbox simulations remain available.
- Django `/admin/` is the framework's staff administration interface. Its
  authentication, permissions and native administration are outside the product
  catalogue rollout; mapping it does not enable staff access or restyle it.
- The static preview and Design Lab are reference surfaces, not alternate
  financial applications or runtime data sources.
- Assistant proposal/simulation interfaces are contracts only. No provider,
  action execution, Open Finance connector or unattended automation is enabled;
  they cannot bypass an unavailable feature's server gate.

## Adoption and verification

The application uses the shared editorial components. The
[dated adoption record](reviews/interface-adoption-2026-10-17.md) preserves
previous rollout decisions, observed test runs and their limits; it is not
a statement about the current test status.

When changing a route or shared interaction, update the inventory above and
inspect the affected desktop and phone screens in both themes. Exercise long
labels, invalid POST recovery, conditional transitions, keyboard selection,
live filters, native fallback, wide tables, contextual Save/Cancel and fixed
navigation clearance. Private history must reauthorize without replaying
POSTs or restoring another user's HTML or draft fields. Use the isolated
[browser runner](../CONTRIBUTING.md#browser-tests) for writes, and record
new validation with its date, scope and remaining gaps.
