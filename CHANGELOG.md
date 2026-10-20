# Changelog

All notable changes to Tuxedo Finance are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and project versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Assistant consultations and exports

- Copy one chat message or the complete conversation as Markdown, with an authenticated native download fallback.
- Consult owned financial workspaces by default and calculate requested monthly CLT scenarios through existing application services, without saving or a page-data checkbox.
- Review transaction edits/deletion in chat before explicit confirmation; retain existing financial validation and ledger rules.


### Fixed

- Keep one verified reference footer in assistant replies, without repeating internal paths at the end of the text. Preserve saved/copied Markdown and inert unverified links; versioned instructions use the same presentation contract.
- Accept documented function calls that omit their optional namespace and retain completed streaming items when the final response does not repeat them. Preserve exact tool-name validation, complete-batch checks, owner checks and confirmation requirements. Keep provider diagnostics limited to fixed validation-stage labels.
- Format assistant replies with a safe local Markdown subset and show truthful thinking/streaming progress without blocking the workspace. Restore the shared spacing between workspace tabs and titles in Planning and Investments.
- Distinguish a locally selected ChatGPT account from installation-level authorization/inference availability, so a retained link does not appear to be a working message connection while its gates are disabled.
- Preserve the real browser origin on native ChatGPT authorization POSTs, retaining Django CSRF checks, opener isolation and no-referrer callbacks. Scope the official authorization redirect allowance to assistant settings instead of changing the global form policy.
- Open the assistant as a fixed overlay without shrinking the workspace or its filters. Keep Context as a compact current-page link, retain structured evidence on the backend, and animate only the cat/orbit artwork gently with reduced-motion support.
- Open the product homepage from the Tuxedo Finance brand in the desktop sidebar and mobile toolbar, preserving the session, unsaved-edit protection and the Home workspace's dashboard destination.
- Use the existing Django financial calendar consistently for invoice due state, confirmed-payment totals/validation and demo confirmation guards, independent of the host timezone. Preserve stored dates and explicit historical cutoffs. Wait for the Accounts entry animation before measuring its unchanged 44px action targets in browser tests.
- Project recurrence from arithmetic source windows and reject fixed schedules above 1,200 monthly occurrences per transaction within the projection horizon. Preserve historical amounts and paid invoices; recover excessive legacy schedules through Transactions with atomic rollback and explicit individual repairs before full reconciliation resumes.
- Correct public guidance for preview captures/sections, version-check guarantees, repository implementation evidence, HTMX licensing, paused import queues, the language endpoint, mobile label sizing and the ordinary-expense catalogue specimen.
- Install pinned frontend tools before repository-tool checks in CI so the Playwright configuration check runs on clean checkouts. Clarify ordinary versus persistent payment-choice keyboard/selection contracts in the owning Forms guide, with presentation linking to that behavior.
- Contain long Home/report identities and selected-category summaries, retain full category labels with comfortable touch targets, and expose wide charts/outlook tables as named keyboard-scroll regions. Keep report-period presets aligned in active and linked states without changing chart data or calculations.
- Preserve filtered origins through category import/delete actions, banking confirmations, nested invoice payment/source editors and inline reward-redemption editing; return to the overview after removing an empty bank. Keep long valid names inside rows, activity, notices, confirmations and searchable choices on phones, without changing accounting values.
- Align Home and Reports shortcuts with their actual scope: reveal the linked account row, identify outstanding invoices including overdue amounts, label the rolling-year controls Last 12 months and retain chart/filter context through source-editor Save/Cancel. Keep the empty-report New transaction shortcut available after period changes with the same return context.
- Remove the misleading Reports shortcut from Home's category-expense summary.
- Align remaining rendered form, filter and action differences with the editorial catalogue: consistent titles/menu targets, compact color controls, adjacent gradient labels, stable read-only import search, grouped actions and cohesive confirmations. Preserve financial precision, native submissions and contextual navigation; correct translated record summaries without changing ledger data.
- Keep invalid catalogue preview controls visible below the sticky header, including shared searchable choices; preserve keyboard recovery, both themes and native fallback.
- Reauthorize private history through server GETs and discard legacy HTMX DOM snapshots so logout and account changes cannot restore another user's cached financial pages. Prevent native restoration of private form values, including without JavaScript, while preserving identity-checked draft, focus, filter and asset recovery.
- Reject unequal same-currency transfers, cash operations before known account openings and cyclic or foreign category parents. Preserve existing financial records and expose read-only opening-date conflict inspection.
- Bound category CSV input, reject malformed or extra/missing columns, and return recoverable field errors without partial imports.
- Keep realized spending, category details and points costs on their reporting FX cutoff. Future rates cannot create realized values or invented remaining planned activity. Empty foreign balances need no rate; nonzero obligations retain their evidence warnings.
- Align the canonical catalogue with paused navigation and icon-only mouse-help dismissal; mark historical reviews and document expense-breakdown coverage.
- Preserve internal Tab/Shift+Tab focus in month panels instead of dismissing them during native focus transfer.

### Added

- Prepare transactions, source categorization, goals and category budgets through bounded assistant tools, with immutable in-chat summaries and separate owner/session-bound confirmation. Reuse canonical financial validation, prevent duplicate confirmations and preserve existing source data.
- Add an operator-only Meu Pluggy Inter card-bill pilot with offline synthetic preparation, one-shot hidden credentials, bounded read-only collection and private daily observation reuse. Preserve all database records and paused import routes; real personal-proxy bill coverage remains to be verified after owner setup.

- Add versioned Tuxedo financial-assistant identity and original personal-finance reasoning premises, with goal/evidence/scenario guidance, methodology provenance and explicit current web/news limitations. Preserve earlier instruction versions; no external research tool or unattended financial action is enabled.
- Add optional catalogue-validated reasoning effort to the subscription assistant. Keep Model and Reasoning effort in a compact Chat settings gear with native labelled choices, mobile clearance and invalid-field recovery; Model default leaves the provider's effort unchanged, without another billing route or automatic model fallback.
- Add selected-account model choices and streamed assistant replies behind a separate default-off inference gate. Require a validated selected model and bounded relevant owned financial context; retain native submission, Cancel, verified local references and bounded completed/partial history. Keep unavailable states honest and retries idempotent; financial changes require separate confirmation and no paid fallback exists. Add guarded synthetic streaming browser fixtures without live account or provider access.
- Prepare owner-scoped ChatGPT account settings and local OAuth authorization, disabled by default. Keep tokens and PKCE in an encrypted private vault, require confirmation in the originating Django session, serialize refresh and preserve local disconnect. A separately approved native account link was observed; it does not itself enable the inference gate or prove live model access and usage limits.
- Add a local assistant foundation with private conversations, an authenticated utility panel and native page, signed bounded financial context and explicit provider-unavailable recovery. Apply its incremental migrations before opening chat. With either provider gate off the composer stays unavailable. Financial consultations are read-only; supported changes use separate reviewed confirmation. No paid fallback, bank connection or unattended financial execution is enabled.
- Document a dated personal Open Finance study for Nubank, Inter and Mercado Pago, including the unresolved 6–8-hour PF production route, resource-specific cadence, costs/consent/local delivery limits and source-preserving reconciliation. Keep statement operations paused; the study enables no bank/provider execution and the developer version is unchanged.
- Add one calendar engine shared by complete-date application fields and the catalogue's entry/card-editor dates. Preserve preferred DMY/MDY application text, ISO helpers, ordinary keyboard editing, invalid POST recovery and native fallbacks; support whole-field activation, a modal keyboard grid, month/year jumps, limits, leap days, touch, both themes and reduced motion.
- Add persisted debit/credit-card appearance with four creation presets, optional gradients on create/edit and custom base colors on edit. Keep owned record selection, cycle/settlement settings, native POSTs and existing clients intact; protect essential preview text from arbitrary color backgrounds. Existing cards receive Graphite without changing financial records; apply the banking migration before starting the updated application.
- Add a catalogue-only credit-card editor with bank/account choices, editable nicknames, four appearance presets and optional custom gradients on edit. Keep required cycle days empty, preserve real card-type/settlement fields and independent native GET forms, and hold preview changes only in the current document without automatically choosing a card.
- Add a canonical visual catalogue for the public homepage, five-destination workspace and entry forms, with local interactions and historical award references. Preserve approved typography/palette and share the adopted presentation with the application; catalogue specimens remain synthetic.
- Add an isolated reporting benchmark for 0, 1,000 and 10,000 synthetic sources, recording latency, queries, financial writes and Python allocation peaks with explicit measurement limits.
- Add a local CSV/OFX statement implementation with explicit mapping, staged review, stable bank-ID deduplication and possible-duplicate warnings; match existing bank movements, confirm invoice payments or record owned-account transfers. Compare stated closing balances without automatic adjustments and undo unchanged batches with guarded source snapshots. Interface operations remain paused pending usability review.
- Split transactions between categories with exact native totals and cumulative installment cents, preserving one financial source while applying allocations to reports, budgets, filters and CSV exports.
- Add monthly category budgets, previous-month copying and recorded/forecast spending; add currency/date goals with named reservations of existing account or monetary cash-pot balances, capped progress and visible shortfalls.
- Add explained local duplicate, subscription-increase, budget-overspend and future-cash-shortage signals with reversible review decisions that do not mutate source finances.
- Add opt-in confirmed credit-card payments, including partial payments, actual account debits and remaining forecast obligations; preserve earlier automatic invoice settlement and guard repeated submissions.
- Add dated local investment price observations, weighted-average remaining cost, realized/unrealized results and explicit fee currency, plus underlying net-worth calculations that include incurred card debt and disclose incomplete valuation evidence. The net-worth interface remains under review.
- Expand synthetic demo data with known opening dates, local prices, budgets, funded goals, review signals and overdue/partial confirmed invoices; future anchors keep unfunded targets instead of inventing current capacity or future confirmed payments.
- Document isolated manual branch testing with a disposable SQLite backup and an owner acceptance checklist; no release, image or version change is published by these additions.

### Changed

- Clarify assistant data sharing, default owned consultations and separately confirmed changes across the security guide, setup examples, technical documentation and both READMEs. Refresh the isolated synthetic preview without publishing a release.
- Remember explicitly chosen assistant model/reasoning effort locally per user and linked account, revalidating capabilities on reload. Keep drafts separate from saved settings, retain native Send persistence and expose retry for failed settings saves. Replace the distorted settings gear with the symmetric design-system icon inside its unchanged 44px target.
- Reduce assistant window chrome with quiet paired controls, one toolbar for history/context/actions, compact message typography and a shallow composer with a single-line model/effort caption. Preserve the approved artwork/motion, accessible labels, 44px activation targets and existing chat behavior.
- Give the assistant a grouped window titlebar with 44px Minimize and Close controls. Minimize keeps the current-document draft, model/effort choices and reply behind an explicit restore tab; restoration reauthorizes the user/session. Close clears temporary composer state and cancels the reply without deleting saved conversation history.
- Refine the assistant into a conversation layout with right-aligned user messages, an independently scrolling transcript and a persistent compact composer. Group header actions, center the empty state and align the composer with a theme-aware focus frame; compact visual badges/buttons retain 44px activation areas. Keep model/context choices and history deliberate; Enter sends, Shift+Enter adds a line, and reading older messages pauses automatic tail following. Preserve native submission, local history, financial drafts and subscription-only provider behavior.
- Refresh the English/Portuguese READMEs with factual copy, prominent preview access and a copyable Docker quick start. Open the static tour directly on the dashboard, with its charts, the editorial five-workspace sidebar/phone dock, secondary Reports tab and a New entry view of the actual transaction form. Keep current synthetic captures in both themes and local typography; preserve legacy anchors, native language links, browser history, no-JavaScript access and keyboard-accessible image inspection.
- Organize frontend style sources by shared/workspace responsibility and form scripts into owning Django partials, preserving the emitted CSS and script behavior. Split frontend contracts into linked responsibility guides with legacy section anchors, and validate local documentation links/anchors in CI.
- Group Django tests inside each app by responsibility with explicit fixture helpers. Split Banking and Investments form/view modules and Transaction consultation/editing views behind stable public imports; extract bounded atomic category CSV imports without changing models, migrations, URLs or financial services.
- Keep frontend/browser configurations with their sources, group browser specs by domain and share catalogue routing. Move local preview maintenance under `scripts/preview/` and new test/coverage/cache outputs under ignored `.local/`, preserving installation data and existing artifacts. Run JavaScript amount/allocation unit tests in CI.
- Apply the approved editorial design across authentication and all five workspaces, including complete forms, lists, confirmations and feedback. Use the same Home, Transactions, Accounts, Investments and Plan destinations on desktop/mobile, with local section tabs, deliberate menus, visible focus and native links; omit decorative destination numbers.
- Open Accounts with a colored institution overview and replace it with one full-width internal bank workspace when selected. Keep consolidated balances visible, a prominent Minimize action, account/card shortcuts, reserves and secondary recent activity. Monetary cash pots retain separate Balance/Available figures and one redemption hint; excluding planning funds never hides balances or debts.
- Open Invoices with an owned-card grid, including empty cards, then each card's filtered history. Preserve independent pagination, confirmed payments, native URLs, contextual origins and redirects for legacy card-filter bookmarks. Expose compact invoice/FX criteria, explain reference-rate direction and keep the invoice month readable on phones.
- Group complete bank-account, card, transfer, FX, loyalty, redemption and payment forms with the same compact native fieldsets as Investments and Plan. Preserve field order, precision, conditional recovery and original native POSTs. Keep long names readable in rows, confirmations, feedback and ordinary choice results; bound the selected bank's sticky title while retaining its full accessible name.
- Use native segmented choices for transaction type/payment and shared searchable records for categories and instruments. Show account/PIX icons, bank markers and saved card miniatures immediately after channel selection; filtering, blur and Tab preserve the payment board. Format only the transaction total from cents while typing, retaining decimal paste, existing amounts and native server submission.
- Include optional category splits in transaction create/edit and distribute exact integer-cent remainders around deliberate amounts. Keep Add category beside its rows with JavaScript and after native Save without it. Preserve bound errors, clear removal labels, one financial event and cumulative installment category totals.
- Keep category groups collapsed initially, with aligned name/type/count rows, ancestor context for filtered descendants and native secondary actions. Level/Type stay visible as segmented GET choices; legacy view bookmarks use the same list. Import, export and deletion remain deliberate actions, with validated Save/Cancel origins.
- Apply consultation text searches dynamically, and choices, dates and ordering immediately, while preserving controls, caret, focus, scroll, Back/Forward and native GET fallback. Keep one primary search and stable Clear/action slots; Transactions uses general category search and compact optional recurrence/date/order criteria, while exact category bookmarks retain labelled context. Month consultation uses localized names and explicit years, ISO fallback, unique-match Enter confirmation and a separate current-month reset where required.
- Use an accessible dialog for internal edited-form departures, retaining browser-owned reload/tab-close warnings. GET filters and chart selections remain read-only view state. Period arrows keep fixed slots and reset actions use a reserved row in the application and catalogue.
- Refine Investments into aligned holdings, contextual updates/history and guided atomic registration; zero configured holdings create no opening cash movement. Keep complete product/asset setup grouped, analyses/configuration in deliberate secondary options, historical source links within their plotted cutoff and readable archived/active catalogues.
- Center Plan on the selected month's available-money outlook and budgets, with backed goal progress and divided reservation-source rows. Keep signals, salary/yield simulations and private drafts under Tools, grouped rule settings, compact entry sheets and locally scrolling comparisons. Distinguish recorded balances from known projections, preserve empty-versus-zero overrides and require explicit draft saving.
- Share one Paper Layers homepage engine with the catalogue. Painted-area hover reveals the five workspace links; click, touch, Enter and Space toggle the focusable bow tie, with Escape, reduced motion and native fallback. Preserve authentication/signup policy, pointer travel to the index, the shorter headline and the decorative underline.
- Keep one canonical catalogue shell, with `#shell` as an alias of `#navigation`, synthetic account/card states and a 960px transaction specimen. Use balanced 44px actions, restrained arrow/color feedback, shared preferred-date calendars and labelled inner table scrolling/print layouts. Application records retain Django validation and the shared record picker rather than the small catalogue-only card-radio exception.
- Adjust saved card gradients with a rotary handle and live preview while preserving precise keyboard control, recoverable errors and the native numeric fallback. Show saved card miniatures in account and invoice summaries as well as transaction choices. Reuse the same persistent instrument board in banking editors, including multiple loyalty cards, invoice awards, points purchases and redemption/IOF sources; retain native checkboxes, search, ownership and financial precision.
- Organize current documentation by responsibility, keep English/PT README content equivalent and separate dated review/validation records from current contracts. Align paused-feature descriptions, the interface map, frontend guide and agent instructions with the implemented workflows.
- Reuse one owned transaction-source list across report charts, shared conversion context and incremental ledger synchronization without repeated unchanged writes. Keep fonts local and document synthetic performance observations with their limits; do not add persisted reporting caches or change financial sources.
- Hide paused Net worth and statement-entry interfaces while preserving their server-side gates, underlying read models and owned read-only import history. Old statement operations, including stale submissions, return to Transactions; Net worth URLs return to Home. No release date is promised.
- Allow an explicit disposable preview for phone testing on a trusted LAN; loopback remains the default and the installation database is untouched.
- Apply incremental migrations for imports, category splits, budgets, goals, price observations, opening dates, confirmed payments, card appearance and per-position planning participation. Preserve existing records, unknown legacy opening dates, automatic card settlement until opted in and initially included planning positions.

### Removed

- Remove the unreleased category graph and its view switch, retaining the native grouped list and compatible filters.

## [0.10.0] - 2026-10-09

### Fixed

- Clarify native updates: back up the active database and apply pending migrations before restarting, so shared dashboard, bank and investment queries use the current schema.
- Separate current investment totals from historical FX gaps, disclose native values and applied rates, and provide dated recovery links and explicit capture of missing historical conversions without replacing saved evidence.
- Keep native-currency investment history available after changing the reporting currency, and skip unnecessary conversion for zero current positions.

### Added

- Delete unused investment assets or archive and restore assets while preserving opening positions, operations and portfolio totals; hide archived assets from Portfolio and Remunerated cash position lists and new entries while retaining historical editors and filters.
- Add investment operation filters for dates, currency and asset class, with retained validation errors, plus position-scoped history and product shortcuts for new operations.
- Document an investment review and a sourced Pierre Finance comparison, including remaining valuation limitations and proposed priorities.

### Changed

- Add the `Asset.is_archived` field with a false default, preserving existing assets and financial records; native installations must apply migrations before restarting. Rehearse container upgrades from v0.3.0, v0.4.0, v0.9.0 and v0.9.1 before publication.

### Security

- Update the CSS development dependency `source-map-js` to 1.2.2, resolving GHSA-68fv-2mgg-jv7q while preserving compiled styles.

## [0.9.1] - 2026-10-03

### Fixed

- Generate one protected IOF expense per reward redemption, backfill existing charges, and show them in Transactions and card reports without duplicating invoices or account debits. Edit the redemption inline in bank history to reconcile its points, reward and IOF sources.
- Add discreet composition links to the contributing transactions, investment operations, opening positions and bank accounts; disclose multiple sources without changing totals or generated IOF edit protection.
- Keep chart composition open after releasing Ctrl or crossing between the chart and panel; highlight its close button, close on a second Ctrl or any outside click/scroll, and preserve internal scrolling and keyboard focus.
- Open repository and quick-start links from the bilingual static tour in a separate tab, including when the tour is embedded in a sandboxed portfolio preview.

### Security

- Remove the vulnerable brace-pattern dependency chain from CSS builds by using the official Tailwind PostCSS compiler, preserving the existing font, colors, component dimensions and keyboard focus styles. Keep the high-severity npm audit gate.

## [0.9.0] - 2026-09-28

### Added

- Add an optional `insert_demo pt|en` command that creates separate demo accounts with localized synthetic financial history, future commitments and saved planning scenarios, random passwords and protection against replacing existing users.

### Fixed

- Point the Docker installation guide to the current README quick start instead of outdated release instructions.

## [0.8.2] - 2026-09-27

### Added

- Add a monthly-plan tax bracket consultation with highlighted INSS, IRRF and reduction bands, plus optional CLT payroll parameters retained in drafts.

- Start new monthly plans with editable Emergency reserve and Investment rows, both at zero, preserving submitted rows and existing drafts.

### Fixed

- Keep contextual help open during unrelated background preview updates.
- Restore automatic INSS and IRRF deductions in monthly planning, using ordinary CLT net salary for the available balance and retaining gross-based percentage expenses. Show the deduction breakdown and preserve legacy drafts until recalculation.

## [0.8.1] - 2026-09-27

### Fixed

- Use the expense reference month in new monthly plans, matching Reports instead of shifting card expenses to the invoice due month. Preserve captured values when opening or comparing existing drafts.

## [0.8.0] - 2026-09-27

### Fixed

- Apply the investment chart scope immediately on selection, retaining the native Filter action without JavaScript.
- Exclude read-only GET filters and chart views from unsaved-operation departure warnings while retaining protection for edited POST forms and simulations.

### Added

- Add an investment Charts tab with Overall, Portfolio and Remunerated cash scopes, historical position evolution and monthly flows.
- Allow additional monthly-plan expenses in BRL or a percentage of gross salary, including saved drafts.

### Changed

- Match investment amount, quantity, unit-price and cash labels to deposits, withdrawals and yields.
- Add previous/next planning-month controls and a full-field native picker, hiding the redundant forecast action when JavaScript is available.
- Clarify yield simulation rate/currency parameters and add accessible duration shortcuts.
- Simplify the salary sandbox to gross salary, a selected-month expense forecast and optional additional fixed expenses, with draft saving kept optional.

## [0.7.0] - 2026-09-26

### Changed

- Use the same previous/next, Current month and All time controls for installment and account/card report charts.
- Place transaction search and the exact category filter together, with matching mobile and keyboard order.
- Remove redundant page-level return links in favor of shared navigation and browser history.
- Reveal investment funding records only after choosing account or points, keep optional fees under Advanced options, and ask for opening unit prices only after a quantity.
- Group yield simulation inputs into three stages, update individual-month rows with duration, and make monthly results and draft saving optional disclosures.

### Fixed

- Keep the selected interface language for one year, alongside the already persistent light/dark theme choice.
- Keep category, bank, investment product and asset filter identifiers usable above 999 in both interface languages.

## [0.6.1] - 2026-09-25

### Fixed

- Keep unsaved-form departure warnings active when a user starts editing before HTMX finishes settling a newly opened page.

## [0.6.0] - 2026-09-25

### Added

- Add exchange-rate editing and confirmed deletion, with user-scoped access and preserved historical conversion snapshots.

### Changed

- Guide initial investment setup before offering New operation, group configured products by bank, and retain a clear Configuration tab for later edits.
- Disable the investment-area simulation shortcut with a gray notice directing users to Planning → Yield simulation.
- Start account/card activity at the current month with independent previous/next month arrows, Current month and All time actions.
- Use browser Back/Forward to restore recent workspace inputs, and confirm departure from edited forms or simulation results.

### Fixed

- Open Export CSV and other option buttons only after deliberate activation.
- Share Back to today controls between balance evolution and monthly cash flow.
- Apply the installment month filter immediately on selection, preserving keyboard focus, scroll and other report filters.
- Open category and subcategory ellipsis menus only on explicit activation, keeping one row menu open and preventing accidental neighboring Delete menus on hover.

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

[Unreleased]: https://github.com/HenriqueMayer/TuxedoFinance/compare/v0.10.0...HEAD
[0.10.0]: https://github.com/HenriqueMayer/TuxedoFinance/compare/v0.9.1...v0.10.0
[0.9.1]: https://github.com/HenriqueMayer/TuxedoFinance/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/HenriqueMayer/TuxedoFinance/compare/v0.8.2...v0.9.0
[0.8.2]: https://github.com/HenriqueMayer/TuxedoFinance/compare/v0.8.1...v0.8.2
[0.8.1]: https://github.com/HenriqueMayer/TuxedoFinance/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/HenriqueMayer/TuxedoFinance/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/HenriqueMayer/TuxedoFinance/compare/v0.6.1...v0.7.0
[0.6.1]: https://github.com/HenriqueMayer/TuxedoFinance/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/HenriqueMayer/TuxedoFinance/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/HenriqueMayer/TuxedoFinance/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/HenriqueMayer/TuxedoFinance/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/HenriqueMayer/TuxedoFinance/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/HenriqueMayer/TuxedoFinance/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/HenriqueMayer/TuxedoFinance/releases/tag/v0.1.0
