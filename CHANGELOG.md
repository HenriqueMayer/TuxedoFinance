# Changelog

All notable changes to Tuxedo Finance are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and project versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.5.0] - 2026-09-21

### Added

- Dedicated investment Operations tab with search, purpose/type/record filters and pagination; portfolio charts precede a contextual history link.
- Custom bank colors with suggested swatches, a corner marker and a color-only edit action beside the bank title.
- One-step previous-screen recovery for contextual page links and cross-area shortcuts, preserving unsent fields, filters, focus and scroll within the current browser tab.
- Direct chart selection: drag time ranges, Shift-click individual bars or slices, read donut sums in the center and clear selections with outside click or Escape.
- Read-only chart composition on Ctrl-hover or keyboard focus, with touch-hold access and user-scoped categories, accounts, products and assets.

### Changed

- Keep Simulate returns last in investment navigation; primary navigation and section tabs clear previous-screen recovery.
- Show opening balance, closing balance and net change for selected cumulative-balance periods; preserve exact monetary cents in selection totals.
- Keep chart selection and composition independent from financial writes, with shared keyboard, touch and no-JavaScript navigation behavior.
- Refresh the bilingual installation instructions and static interface preview for this release.

### Removed

- Manual chart range selectors, instrument click drilldowns and the redundant "Where the money goes" chart.

## [0.4.0] - 2026-09-20

### Added

- Individual category-group disclosures and Collapse all / Expand all controls, initially expanded and preserving filtered child results.
- Remunerated cash products, partial account reservations and explicit planning participation, preserving complete balances and liabilities.
- Named private planning drafts, reviewed snapshots of upcoming commitments and monthly investment-yield simulations.
- Five-area navigation, grouped bank/account and portfolio tables, and category hierarchy/type/usage controls.
- Explicit spreadsheet-oriented CSV exports and predecessor-image Docker upgrade rehearsals.

### Fixed

- Keep navigation labels and SVG carets aligned, restore clear surface and metric groups, and adapt bank tables and planning sheets to narrow screens.
- Version CSS and JavaScript by content and recover stale HTMX tabs on their next GET, without replaying POSTs or discarding invalid form responses.
- Protect investment assets with opening positions or operation history from individual and bulk deletion (FIN-11).
- Apply the saved date-format preference across the application through one shared date control (FIN-12).
- Base bank projections on actual cash settlement; preserve opening investment positions in historical series.
- Report invalid planning rows instead of silently dropping them; retain complete no-JavaScript entry paths.
- Stop forecast navigation before incomplete future months and retain scroll/focus through HTMX chart updates.
- Aggregate bank and loyalty balances without a query for every displayed row.
- Clarify supported release upgrades versus the historical pre-release schema reset, and create native environment files privately without overwriting a signing key.
- Disable the unused Gunicorn control socket so container startup does not depend on an unavailable home directory.

### Changed

- Restore grouped cards for financial workspaces, reveal navigation options on hover and move explanatory copy into shared contextual help beside headings and field labels.
- Share compiled application styles with the canonical visual catalogue and refresh the bilingual preview with 14 synthetic screenshots, including Planning.


## [0.3.0] - 2026-09-17

### Fixed

- Banking list/detail routes redirect anonymous visitors to login before
  synchronizing the ledger. Docker health checks support allowed subdomains,
  and container backup instructions export private data outside the checkout.

- Unified question-mark help across Reports and Sandbox: hover opens one
  readable box, leaving or clicking outside closes it, and mouse clicks never
  pin it. Structured formulas, keyboard/touch support and the mandatory help
  design contract replace the narrow, persistent report disclosures.

- Searchable form choices now bring their input and results into view when
  reached by keyboard, including credit cards near the bottom of a transaction
  form. Long lists keep the active option visible and adapt to short viewports.

- Searchable choices now visibly highlight arrow-key navigation, reopen after
  Escape, and confirm only with an explicit selection without submitting the form.

- Static preview language links now target HTML files explicitly, allowing
  English/Portuguese navigation when the tour is opened locally with `file://`.

### Added

- Docker and Compose packaging with Gunicorn, compressed static assets,
  persistent SQLite volumes and a non-root runtime; documented local builds,
  versioned release images, configuration, updates and backup/restore (#18).
- Isolated Docker browser and lifecycle checks, plus a release workflow that
  validates amd64/arm64 images before publishing to GHCR with matching
  installation assets for the no-clone setup.

- Shared keyboard-search controls for record selectors, searchable multi-select
  checkboxes, and a mandatory form contract for contributors and agents.

- Portuguese README with reciprocal language links and version validation for
  both English and Portuguese editions.

### Changed

- Reports now show live bank cash, the identified month's projected inflows
  minus outflows, and the existing full-window net change with an accessible
  period explanation. Removed the best-month card.

- Conditional creation choices now wait for explicit selection across transaction,
  investment, banking and sandbox forms. Card details wait for a card, CLT starts
  unchecked, and error recovery plus native no-JavaScript controls are preserved.

- Static interface tour now matches the black/graphite dark theme, with all 12
  synthetic screenshots refreshed from the current application and bilingual
  captions aligned with monthly dashboard activity and transaction navigation.

- Transactions now use counted type cards, contextual category choices and
  recurrence shortcuts, with progressive date filters and no-JavaScript
  navigation (FIN-10). Type cards are compact and stay on one line; same-page
  HTMX updates retain viewport and keyboard focus instead of jumping to the top.

- Public homepage now uses factual bilingual copy, access links, six feature
  rows, and a full horizontal cat photograph in a translucent double frame, without sample balances or promotional cards (FIN-9).
- Dark-mode foundations now use neutral black and graphite throughout the
  application, with readable controls and unchanged light/financial palettes (FIN-9).
- Removed the promotional slogan from the shared footer.
- Contained salary-table accessibility labels within their scroll area and
  allowed the public navigation to wrap for no-JavaScript language controls.

- `npm run test:e2e` now manages a disposable local Django server and database;
  local development and CI share the same isolated browser-test workflow.

## [0.2.0] - 2026-09-03

### Added

- Bilingual static interface tour for GitHub Pages, with reproducible synthetic
  screenshots, accessible image expansion and an isolated preview test suite.
- Authenticated, non-persistent Salary Sandbox with automatic 2026 CLT rules,
  manual deductions and monthly-budget planning.
- Monetary investment-yield entry by new total balance, including a
  non-persistent preview and save-time server recalculation.

### Changed

- Reorganized project documentation, design-system references and category
  collections around consistent, descriptive paths.
- Expanded the database documentation with the current entity relationships and
  the posting flows for transactions, transfers, investments and rewards.
- Established progressive disclosure as the project-wide rule for conditional
  forms, filters, pickers, menus and category-driven flows.
- Improved Reports and Investments chart navigation, hover and keyboard
  interactions, and low-value axis labels.
- Renamed the runtime data-directory setting from `CASHFLOW_DATA_DIR` to
  `TUXEDO_DATA_DIR`; existing installations that customize the database
  location must update their environment configuration.

### Fixed

- Loyalty entries now hide points-purchase payment fields for invoice awards
  and clear values from the inactive invoice or purchase branch when the entry
  kind changes (FIN-6).
- Investment operation fields now preserve server-side validation errors on
  initial render and clear stale inactive yield values after deliberate mode,
  asset or operation-type changes.

### Removed

- Obsolete design sketches, unused source-brand duplicates and an unnecessary
  static-directory placeholder.

## [0.1.0] - 2026-08-23

### Added

- Local-first personal-finance workflows for transactions, categories, banks,
  accounts, cards, invoices, exchange rates, investments, dashboard and reports.
- English and Brazilian Portuguese interfaces with user-selectable locale,
  currency and date preferences.
- Responsive light and dark themes backed by a documented design system and
  accessible financial-semantic colors.
- Server-rendered SVG reports and investment charts with mouse and keyboard
  tooltips.
- Reproducible Python and frontend dependency lockfiles, automated Django
  checks, coverage, dependency auditing and Playwright browser smoke tests.

### Changed

- Reworked the complete presentation layer around readable Inter typography,
  higher contrast, compact responsive navigation and consistent form patterns.
- Made HTMX a local progressive-enhancement dependency while preserving native
  navigation, downloads, forms and no-JavaScript fallbacks.
- Expanded the public README and technical documentation for installation,
  architecture, data ownership, frontend behavior and local operations.

### Fixed

- Removed navigation flashes during enhanced page transitions.
- Improved dark-theme language selection and investment text contrast.
- Aligned investment pagination, chart interactions and movement ordering with
  the rest of the application.

[Unreleased]: https://github.com/HenriqueMayer/TuxedoFinance/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/HenriqueMayer/TuxedoFinance/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/HenriqueMayer/TuxedoFinance/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/HenriqueMayer/TuxedoFinance/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/HenriqueMayer/TuxedoFinance/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/HenriqueMayer/TuxedoFinance/releases/tag/v0.1.0
