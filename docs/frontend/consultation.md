# Frontend consultation and live filters

[Frontend index](../frontend.md) · [Interface map](../interface-map.md)

## Live consultation filters

All consultation searches apply while typing or deleting (300 ms debounce).
Short choices, record selections, committed dates and ordering apply immediately.
Show Clear beside the controls when a filter is active. No-JavaScript GET forms
retain their submit button; network failure reveals it as a recovery path. POST
operations and scenario execution remain deliberate actions.

Reuse `static/js/live-filters.js` with a stable GET form ID, `data-live-filters`,
`data-live-results="result-id"`, and `hx-boost="false"`. Mark text inputs with
`data-live-search`, choices/committed-date wrappers with `data-live-change`, and
fallback submit buttons with `data-live-submit`. Result counts and Clear links
outside the result island use a stable ID and `data-live-fragment="form-id"`.
Clear links also use `data-live-reset` to reset controls synchronously before
the GET, so immediately typing a new query cannot revive the old filters.
Filter/pagination links use `data-live-link="form-id"`; pill changes may use
`data-live-set`/`data-live-value` to retain unsent search text. Do not attach a
second HTMX auto-submit handler to the same form.

Keep the controls in the document, replace only results/metadata, abort stale
requests, and initialize shared forms/help after replacement. Do not rewrite
partial dates or composition input. Preserve caret, keyboard focus, nonzero
scroll and surviving account/reserve disclosures. Category branches intentionally
follow search expansion; action menus never inherit an open state through a
replacement. One typing session creates one history entry; explicit choices and
Enter create separate entries. Back/Forward restores fresh owned GET results
and controls without triggering unsaved-operation warnings. Load the helper after
`previous-workspace.js` so edited POST departure guards retain priority.
Live GET forms do not capture or restore draft fields in workspace snapshots:
their applied URL and fresh history response own the controls and results.
Leaving during a pending search and returning therefore restores the last
applied query, while unsent POST drafts and simulation rows keep their existing
restoration behavior.


## Compact consultation bars and month names

Transactions, Categories, Invoices, Exchange rates, investment positions/history
and financial goals use `consultation-bar`, `consultation-search`
and `consultation-actions`. Keep one primary text search; place less frequent
criteria in a deliberate native `details.filter-disclosure`, except for the
approved always-visible families below. Its active count
and nearby Clear refresh independently of the controls. Newly returned field
errors reopen the disclosure without moving focus or page position. Criteria
stay complete in native GET submissions. Transaction search already includes
category and split-category names, so the disclosure does not repeat a category
picker. Existing exact-category URLs retain a named, individually clearable
context and their original GET semantics. Date, recurrence and ordering share
one compact row when space permits, then wrap at narrow widths. Month triggers
use the same paper background as the adjacent consultation fields.

Investment positions/history and financial
goals add `.consultation-stable`. Search,
Filters and the reserved Clear slot share a rail on wider screens. Small screens
keep search above a fixed action row. Only the native summary is positioned in
its slot; opening the complete criteria adds a full-width row below it. Numeric
active badges and screen-reader descriptions update independently. Keep the
native submit fallback in its own row, including after a failed live request.

Read-only import history has no optional criteria. Its
`consultation-search-only` variant reserves a narrow Clear slot beside the search
instead of leaving an empty Filters track. The input's width and position stay
fixed when Clear appears; native GET submission keeps its separate fallback row.
This presentation does not enable the paused statement-import workflow.

Invoices and Exchange rates use `bank-consultation`, exposing their short
criteria in a compact responsive grid. Invoices keeps month, bank and status
visible; Exchange rates keeps source/target currencies and date bounds visible.
Search, field IDs, active counts and Clear retain the same live GET and native
fallback contracts; no disclosure must be opened to reach these criteria.

Categories are the deliberate exception to the optional-criteria disclosure:
Level and Type remain visible as native segmented radio groups beneath the name
search. Their GET names/values are unchanged (`level`: empty, `top`, `sub`;
`type`: empty, `INCOME`, `EXPENSE`, `unclassified`). Each group has a real legend,
one checked choice and native arrow/Space navigation. `live-filters.js` applies
changes immediately and restores choice state by name, type and stable value;
Clear selects the explicit empty-value All choices. Search, focus, caret,
history, hierarchy context and contextual action URLs keep the shared live
contract. The reserved Clear slot does not change the rail when its link appears.
The groups stack on narrower screens and use two columns on mobile; All levels
spans the first row so longer labels remain readable.
An ordinary GET submit remains available without JavaScript or after failure.

Transactions adds `.transaction-consultation` with its existing stable tracks.
At viewport widths of at least 1440px, search/month, type choices, Filters and
Clear share one rail. Smaller desktop layouts use two rows, and mobile uses
explicit stacked tracks rather than content-dependent wrapping. The month
control reserves 12rem, More filters 8.75rem and Clear 7.5rem; type counts reserve at
least six numeral widths and the criteria indicator keeps its own fixed box.
Clear's empty slot remains when its link is absent, without rendering an inactive
action or adding a Tab stop. Type choices occupy equal 44px-high cells; their
labels and counts stack on smaller screens. Type and recurrence choices use
soft selected backgrounds and restrained outlines, keeping semantic income/
expense text colors and unchanged control geometry. Invalid date/choice borders
take precedence over the softer default outlines in both themes.

Only the native Filters summary is positioned in its assigned action slot. Its
fields remain in document flow in the following full-width grid row, so opening
criteria increases the panel height without redistributing the search or other
toolbar controls. Apply has its own row for native submission and request-failure
recovery. Keep the same owned field names, canonical values, focus and history
behavior when modifying this layout; stable slots are not a new filter API.

`html:has(#transaction-filters)` alone sets `scrollbar-gutter: stable`. This
reserves the viewport gutter for classic scrollbars across long and short
transaction lists without forcing an always-visible scrollbar. Overlay scrollbars
do not consume this space; see the
[CSS Overflow gutter rules](https://drafts.csswg.org/css-overflow-3/#scrollbar-gutter-property).
Investment and Planning regions independently opt into the same stable gutter
through `.finance-workspace`; Dashboard, Reports and the other workspaces retain
their existing gutter rules.

Geometry regressions compare control dimensions and document coordinates, plus
the actual `body.app-layout` width, across type changes, search counts, Clear,
month captions,
disclosure expansion and Back/Forward. An explicit expansion may change the
form height; a shorter result set may legitimately clamp the viewport's scroll
offset. Test keyboard input, both themes and languages, responsive breakpoints
and native GET fallback, including the one-rail layout at 1440px without
JavaScript. Two additional classic-scrollbar cases cover light and dark themes:
they launch Chromium without its headless scrollbar-hiding argument, disable
overlay scrollbars, and require a positive rendered scrollbar width on the long
list. The reserved gutter is measured as
`innerWidth - document.body.getBoundingClientRect().width` for both long and
short lists, with unchanged main and toolbar geometry
through keyboard type changes. Root `clientWidth` is diagnostic only:
[CSSOM View](https://drafts.csswg.org/cssom-view/#dom-element-clientwidth) defines
it as viewport width excluding a rendered scrollbar, so it may grow when that
scrollbar disappears even while the empty gutter remains reserved. Each classic
case attaches JSON with root/body/layout/main measurements and computed gutter
values for the long list and each type state.
These checks exercise the runner's bundled Chromium and viewport settings;
retain acceptance on the owner's desktop and mobile browsers for their native
scrollbar, scaling and input behavior.

`partials/month_filter.html` retains the native ISO month input and optionally
uses the shared Django field renderer. `month-filter.js` enhances only marked
consultation controls: open a bounded panel deliberately, type a translated
month name, inspect/edit its year and confirm with Enter. Internal popup
scrolling and deferred scroll events from unrelated search inputs do not dismiss
the panel; actual document/ancestor movement and outside interactions still do. A unique textual match
may confirm directly only on this month choice (`data-search-auto-single`);
ambiguous input needs explicit arrow selection. Ordinary financial record
pickers retain their existing keyboard contract. Both clear actions reset the
canonical ISO value without validating an unused draft year. Closed draft-year
controls are disabled so their native constraints cannot block fallback GET
submission. Escape, outside activation and Tab-away dismiss the panel;
internal Tab/Shift+Tab moves keep it open. Use the focus event's `relatedTarget`
for internal moves: `activeElement` can briefly be the document body while native
focus is transferring. Background updates preserve controls. A required monthly workspace may explicitly
provide `month_reset_value` and `month_clear_label` to the partial: Planning uses
the current ISO month and the label This month. This opt-in changes only that
reset action; optional filters elsewhere still clear to all months. Never apply
an unused invalid year draft when resetting.
No JavaScript keeps the native month input and ordinary submit fallback.

Dashboard and Reports retain their existing period controls and presentation.
