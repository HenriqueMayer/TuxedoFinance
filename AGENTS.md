# Tuxedo Finance contributor contract

Read `CONTRIBUTING.md` before changing the application. Technical documentation
and code use English; interface strings must have English and Brazilian
Portuguese translations.

## Working scope and sources

Investigate accessible facts before asking questions. Reuse confirmed scope and
resolved decisions; reopen only an affected, unresolved requirement. Preserve
unrelated working changes, installation data, `.env`, databases and backups.
Implementation does not authorize publication, merge or release.

Read the guide that owns the change instead of treating a dated review as the
current specification:

| Change | Canonical reference |
|---|---|
| Setup, checks, generated assets and contribution workflow | [Contributing](CONTRIBUTING.md) |
| Routes, shared components and visual exceptions | [Interface map](docs/interface-map.md) and [Design Lab](docs/design-system.html) |
| Interaction and accessibility behavior | [Frontend guide](docs/frontend.md) |
| Financial rules and ownership | [Data model](docs/data-model.md) and the owning [app guide](docs/README.md#per-app-reference) |
| Runtime, stored data and recovery | [Operations](docs/operations.md) |
| Historical evidence and measurements | [Review index](docs/reviews/README.md) |

When changing interface behavior or domain presentation, update its owning
technical guide, add a focused code comment for non-obvious rules and cover the
behavior with an appropriate regression test. Update this contract only for
application-wide obligations. Keep validation results in dated reviews, with
their scope and limits, rather than copying test counts into current contracts.

## Mandatory form behavior

Use the approved editorial components across product screens; the
[interface map](docs/interface-map.md) records route families and exceptions.
Reuse shared panel/action/field classes instead of adding per-page pills or
pickers. Complete dates use the shared preferred-date/calendar component.
Keep monetary cents entry opt-in: quantities, rates, FX, loyalty units and
empty-versus-zero simulation overrides retain their own precision and meaning.

Every new or changed form must follow the [shared form contract](docs/frontend.md#keyboard-and-choice-contract).

- Use `partials/form_field.html` for ordinary Django fields. It automatically
  enhances model choices through `form_control`; do not implement another picker.
  Handwritten record selectors must use `data-search-select` and a stable ID.
  Keep submitted record identifiers unlocalized, including values above 999.
- Keep single boolean controls beside their label and help in the shared
  checkbox row. Preserve native checked values, Space activation and POST errors.
- Preserve native short choices, Tab/Shift+Tab, visible focus, Enter/Space
  activation, and the shared searchable-choice keyboard behavior.
- Payment instruments opt into the shared persistent choice board: its compact
  search filters the visible miniatures, while blur/Tab preserve the board and
  query. Escape clears the query, never the committed record. Ordinary model
  choices retain their close-on-blur behavior. Multiple-card choices reuse the
  same artwork with native checkboxes: Space toggles the focused record, and
  filtering must preserve selections outside the visible results.
- When a user reaches or opens a searchable choice, keep its input and results
  in the viewport without moving focus. Scroll long results internally; preserve
  page position during initialization and background refreshes.
  Fixed popups opt into `data-search-choice-viewport` so shared choices reveal
  their results by scrolling inside the popup instead of moving the document.
  Ordinary result labels wrap in the list, including names without spaces;
  keep their full text and at least 44px targets. Payment miniatures retain
  their own compact identity presentation.
- Start new conditional choices empty, and conditional checkboxes unchecked.
  Preserve bound POSTs, edited records and explicitly selected shortcut context.
- Reveal dependent controls only after the relevant choice. Keep inactive
  controls out of the Tab order, clear incompatible values after deliberate
  transitions and preserve server errors for recovery, including nested groups.
- Keep native controls and complete submissions working without JavaScript.
  Entry forms use `novalidate` and rendered Django errors. Ownership,
  compatibility and accounting validation remain on the server.
- Add browser coverage using real keyboard events for changed interactions,
  including invalid responses and transitions. Inspect focus/selection in both
  themes. Include the contract in future form reviews.

## Mandatory help icons

Every new or changed question-mark help icon must follow the
[shared tooltip contract](docs/frontend.md#question-mark-help). Reuse
`partials/help_popover.html`; open on icon hover or keyboard focus; mouse help closes immediately when the
pointer leaves the icon, including entry into its text. Dismiss on outside
click/Escape, and never pin mouse-clicked help. Preserve touch and
no-JavaScript access. Background updates outside the help owner must preserve
open help. Use the shared readable width and structured copy; test
real interactions, viewport bounds, both themes and HTMX initialization.

## Navigation and departure

Use shared navigation, section tabs and browser Back/Forward for page navigation.
Do not add redundant page-level "Back to" links. Read-only GET filters and chart
visualization changes must not trigger unsaved-operation departure warnings;
preserve those warnings for edited POST forms and simulation results. Keep form
Cancel actions and date-reset controls, which have separate purposes.
Period navigation keeps previous/next in fixed slots. Reset belongs in its own
reserved row; appearing reset actions and unavailable bounds must not move or
exchange the arrows. Internal departure confirmation uses the shared accessible
dialog; tab-close and refresh warnings remain browser-owned.

The same five direct destinations appear in the desktop sidebar and mobile
bottom navigation. Keep secondary pages in the owning workspace's section tabs
or deliberate options; do not restore hover submenus on primary navigation.
Fixed navigation must not cover focused form controls, searchable choices or
the last page action. Save/Cancel preserve an explicit, validated local origin
and its filters; ownership checks remain on the destination. Never infer a
return destination from Referer.

## Private history and drafts

Financial HTML must not enter HTMX's DOM history cache. Back/Forward restores
through an authorized server GET; clear legacy HTMX cache entries and keep any
small form/location snapshots scoped to the current user. Test logout, anonymous
history, user changes, another tab and legacy caches without replaying POSTs.
Native BFCache returns must also reauthorize through GET before restoring state;
cover persisted documents explicitly rather than relying only on cache headers.
Editable private POST forms use `autocomplete="off"` so native history cannot
restore another user's unsent fields onto fresh HTML, including without JavaScript.
Reset history forms to authorized defaults before applying a matching snapshot;
preserve explicit authentication autocomplete on login/signup.

## Deliberate menus and chart inspection

Option menus (including Export CSV, project links and account actions) open
only through deliberate click, touch or keyboard activation.

Row ellipsis menus (`details.compact-menu`) open only through deliberate
activation: click, touch or keyboard. Never open or switch them on hover or
focus alone. Keep one row menu open at a time, retain native `details` behavior
without JavaScript, and preserve outside-click, Tab-away and Escape dismissal.
Primary navigation and question-mark help retain their separate contracts.
Follow the [compact row-action contract](docs/frontend.md#compact-row-action-menus).

Chart composition panels open with Ctrl over a mark or a touch hold and remain
open after key release or pointer travel. Keep scrolling inside the panel,
keyboard focus and a prominent close action; dismiss on another Ctrl press,
Escape, any click or scroll outside the panel, Tab-away or replacement of the
owning chart. Suppress reopening during the Ctrl press that dismissed it. Preserve unrelated HTMX updates.
Keep composition source links discreet and scoped to the shown amounts: a single
source opens its existing editor/context; multiple sources use a deliberate
native disclosure. Preserve Tab access, user ownership, generated-operation
edit locks and browser Back/Forward. Never pick an arbitrary operation for an
aggregate row. Question-mark help and ordinary chart value tooltips retain their
own contracts.


## Dynamic consultation filters

All read-only searches and filters apply dynamically with JavaScript. Reuse
`static/js/live-filters.js`: debounce text typing/deleting, apply choices,
committed dates and ordering immediately, and show Clear near active controls.
Preserve stable controls, caret, keyboard focus, scroll, owned disclosures and
browser Back/Forward. Retain an ordinary GET submit fallback without JavaScript
or after request failure. Keep POST writes and simulations explicitly submitted.
Follow the [live consultation contract](docs/frontend.md#live-consultation-filters)
and test real keyboard interactions, both themes, mobile, and native fallback.

Consultation bars keep one primary text search and optional criteria in a deliberate
native `details.filter-disclosure`, with active counts and Clear beside it.
Categories instead keep their short Level and Type criteria always visible as
native segmented radio groups; preserve the same GET values and stable Clear slot. Use
stable slots for search, the filter trigger and Clear; optional criteria expand
below without redistributing that control rail. Use
`partials/month_filter.html` for named-month consultation: retain the native ISO
field/no-JavaScript submission and reuse the shared choice enhancement. Direct
Enter confirmation of a unique textual match is an explicit month-only opt-in;
ordinary financial record selectors retain their existing arrow-selection rule.
Invoices intentionally expose their compact month, bank and status criteria;
Exchange rates exposes currencies/date bounds. These approved exceptions retain the same
dynamic GET, stable Clear, keyboard and native-submit contracts.
Planned, unavailable resources stay out of app navigation and account shortcuts;
track their redesign in documentation while preserving their server-side gates.

## Verification and handoff

Run browser tests with `npm run test:e2e`, which owns a disposable database and
loopback server. Never point browser tests at the developer's database or server.
Use isolated settings for Django/tooling checks as documented in Contributing.
Keep Django tests under their owning app's `tests/` package, grouped by
responsibility; import support fixtures explicitly and keep test classes out of
`tests/__init__.py`. Preserve discovered app/class/method identities during moves.
View/form package exports preserve public imports, not mutable globals: patch
the implementation module where a dependency is looked up.
Keep E2E specs in their domain folders and reuse the shared catalogue/path
helpers. New tool outputs belong under ignored `.local/`; never relocate or
delete installation data or old artifacts as part of changing output paths.
Use the npm entry points so explicit test configurations and isolation apply.
Run applicable Django checks and `git diff --check`; rebuild committed CSS and
translations when their sources change.

For interface work, inspect the rendered desktop and phone layouts in both
themes, including long names, expanded controls, invalid responses and final
actions above fixed navigation. Pair visual evidence with real keyboard tests
and native fallbacks. Report what was checked and any material gaps; do not
present an earlier test run as current verification.
