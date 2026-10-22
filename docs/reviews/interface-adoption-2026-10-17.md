# Interface adoption and validation — 2026-10-17

> Historical record. This preserves the successive interface rollout checks
> recorded on 2026-10-17; counts describe their individual runs, not the
> current checkout or a cumulative total. Current routes and obligations live
> in the [interface map](../interface-map.md), [frontend guide](../frontend.md)
> and [contributor contract](../../AGENTS.md). Later corrections supersede
> earlier presentation descriptions without changing the evidence below.

## Adoption and verification

The route families and shared components above were mapped and aligned on
2026-10-17. The application now uses the shared editorial stylesheet, compact
controls/actions, single-checkbox rows, full-date calendar and Paper Layers
homepage. Family-specific templates retain their controls, financial rules and
routes; paused features retain their server gates.

Initial adoption validation:

- 657 Django tests passed, including native attributes, owned record IDs,
  Decimal precision, calendar preferences and invalid/bound checkbox recovery.
- 19 Python tooling tests and 8 amount-entry JavaScript tests passed. Django
  checks, migration drift, version consistency and `git diff --check` passed.
  CSS and compiled Portuguese translations reproduce from their sources.
- The browser suite ran in isolated shards, with focused reruns after fixes.
  Coverage includes both themes, English/PT, desktop/mobile, real keyboard
  selection, invalid POST recovery, conditional transitions, date/filter GETs,
  private history, menus/help/charts and no-JavaScript forms. Six existing
  statement-import cases remain skipped while their feature is under review.

### Rendered comparison follow-up — 2026-10-17

The follow-up navigated the rendered application using disposable synthetic
profiles and compared captured screens with the current catalogue. The route
check covered 97 reviewable GET destinations per profile, including create,
edit, detail and confirmation variants. Screenshots covered public/authentication
pages and all five workspaces, their forms, expanded filters and secondary
tools; focused mobile and light/dark passes checked the shared components.
Route health is separate from visual inspection and does not certify every
possible financial state or assistive-technology combination.

Confirmed differences were corrected at their shared source:

- Use the common page-title scale, balanced header option buttons and 44px row
  menu targets; preserve native deliberate menu activation.
- Keep color fields compact and gradient checkbox labels adjacent. Group
  investment header actions, align salary/month controls, and use quiet Cancel
  links and cohesive confirmation panels.
- Give read-only import history a stable search/Clear rail with complete native
  GET fallback. Keep long transaction amounts and currencies together without
  forcing the page wider on mobile.
- Translate the observed-price Asset label and loyalty confirmation directions;
  show money rather than zero units when confirming a monetary operation.
  Keep English transaction/category CTA labels in sentence case and remove
  outdated catalogue copy describing the application as unchanged.

Validation after these corrections:

- The complete Django suite passed 659 tests. Two additional focused loyalty
  confirmation tests passed after their introduction; they were not part of
  that full-suite discovery. Django checks, migration drift and version
  consistency passed.
- 117 selected browser cases passed through the official isolated runner. They
  cover revised components, both themes, English/PT, desktop/mobile geometry,
  real keyboard input, invalid POST recovery, native GET/POST fallbacks,
  contextual Cancel and private Back/Forward restoration. The complete browser
  suite was not rerun in this follow-up.
- CSS and compiled Portuguese translations reproduce from source, and
  `git diff --check` passes. No model migration or financial calculation change
  was required by this follow-up. Personal data and paused-feature gates were
  preserved.

### Workflow refinements — 2026-10-17

The refinement keeps bank summaries visible and opens one bank inline,
exposes compact invoice/exchange criteria, and explains exchange direction in
the fields themselves. Payment miniatures remain visible outside their search
input; category allocation distributes exact cents across automatic rows while
preserving deliberate amounts and recoverable server errors. Internal departure
confirmation uses the shared dialog, while browser-owned unload warnings remain
native. Period arrows keep their positions when the reset action appears.

The practical review replaced the retained bank grid with a full-width internal
workspace. A visible Minimize action returns to the overview to choose another bank.
It also removed decorative navigation numbers and the duplicate category picker,
aligned month-control backgrounds, compacted the remaining transaction criteria,
and placed Add category next to its allocation rows. The public headline and
catalogue use the shorter approved wording with its existing underline.

Validation for this refinement:

- The most recent complete Django run before this additional interface review
  passed 669 tests. This review passed 84 focused Django tests, 19 Python tooling
  tests and 16 JavaScript calculation/amount-entry tests. Django checks,
  migration drift and version consistency passed.
- 100 selected browser cases passed in the practical review with the official
  disposable runner,
  covering keyboard/focus, both themes, desktop/mobile, invalid POST recovery,
  exact-cent allocation, persistent payment choices, contextual navigation,
  private/contextual history, native fallbacks and an index of 40 owned banks.
  Current screenshots were inspected at desktop and mobile widths. The complete
  Django and browser suites were not rerun in this practical review.
- CSS and compiled Portuguese translations reproduce from source, and
  `git diff --check` passes. Financial ownership and accounting validation remain
  on the server. Personal data and paused-feature gates were preserved.

Review each family in both themes, English/PT, desktop/mobile and real keyboard
use. Exercise invalid POST recovery, conditional transitions, record selection,
live filters, native fallback, wide tables, chart inspection and contextual
Save/Cancel. Private history must reauthorize without replaying POSTs or exposing
another user's HTML or draft fields. Use only the disposable
`npm run test:e2e` environment for browser writes; see
[Contributing](../../CONTRIBUTING.md#browser-tests). Keep this structural map and its
observed validation current when changing a route or shared interaction.

### Complete finance subareas — 2026-10-17

The Investments follow-up groups complete product/asset registration into
identity, valuation/opening and funding, compacts the catalogue's secondary
actions and exposes an owned asset criterion in price consultation. Plan
highlights backed goal progress and divided source rows, pairs signal rules
with their thresholds, and preserves the reviewed consultation when editing a
source. Salary/yield tools reuse the compact entry layout; draft comparisons
retain the workspace width and local table scrolling. All original financial
fields, native submissions, precision and server validation remain authoritative.

The scoped verification passed 250 Django tests across Investments, Planning,
Sandbox and shared interface rendering, plus version/check/migration-drift
checks. Selected browser journeys cover both themes, desktop/mobile, keyboard,
invalid recovery, contextual returns, native forms and explicit scenario saving.
CSS and compiled Portuguese translations reproduce from source. This follow-up
did not rerun the entire repository test suite or change a financial model.

### Practical viewport follow-up — 2026-10-17

Fresh review used 20 products/36 assets, long source/goal names, short phone
viewports at 360/390px and desktop at 1280/1440px, in both themes. It corrected
overflowing institution/position/goal headings and reservation context, catalogue
menus opening outside the phone, clipped record-choice labels and a saved-draft
name field compressed by adjacent actions. Short catalogue rows remain compact;
source labels lead with the account/pot and setup copy names Accounts.

250 scoped Django tests and 25 selected browser cases passed, including keyboard,
invalid responses, filters, archiving, explicit draft actions and native forms.
The full repository suites were not rerun. Financial definitions, source
identifiers, precision and owned return destinations remain unchanged.
