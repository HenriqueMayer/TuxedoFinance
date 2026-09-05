# Changelog

All notable changes to Tuxedo Finance are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and project versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Portuguese README with reciprocal language links and version validation for
  both English and Portuguese editions.

### Changed

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

[Unreleased]: https://github.com/HenriqueMayer/TuxedoFinance/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/HenriqueMayer/TuxedoFinance/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/HenriqueMayer/TuxedoFinance/releases/tag/v0.1.0
