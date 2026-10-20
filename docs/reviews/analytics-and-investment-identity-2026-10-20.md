# Analytics and investment identity — 2026-10-20

This dated review records the Analytics and position-identity implementation in
the unreleased working tree based on `cc110a8`. Earlier unrelated local changes
were retained. Current contracts live in [Analytics](../apps/analytics.md),
[Investments](../apps/investments.md#position-appearance),
[navigation](../frontend/navigation.md) and [the interface map](../interface-map.md).

## Scope and resulting behavior

- Add Analytics as the sixth primary destination, with Finances and Investments
  sections. The six mobile destinations retain full accessible identities,
  compact English/Portuguese labels, text of at least 10px and 44px targets.
- Move category expenses, financial charts and the six-month outlook out of
  Home. Home retains availability, monthly indicators, account/invoice previews
  and a selected-month analytical shortcut. Existing chart services, source
  attribution, dated FX and position-valuation rules remain authoritative.
- Preserve the former report and investment-chart entries as compatible
  redirects, including their period/scope context. Source composition continues
  to use the existing signed, owned endpoint and contextual editor returns.
- Expose My investments, History, Prices and Setup directly. Local prices and
  configuration keep their existing financial meaning and validation.
- Add twelve curated position emojis through `PositionAppearance`, keyed by
  user, product and asset. Missing preferences display General. Guided entry
  accepts an icon; existing positions offer an explicit Personalization Save.
  Changing an icon does not post or synchronize a financial operation, change
  planning participation or alter another position of the same asset.
- Align the current guides, contributor navigation contract, Design Lab and
  bilingual public preview. Existing README and preview fragment/image aliases
  remain available. The public bow-tie's five feature highlights remain distinct
  from the six primary workspace destinations.

The financial regression suites retain split-category attribution,
installment/recurrence projection, invoice credits and payments, FX dates and
missing-rate warnings, missing investment prices and dated valuation cutoffs.
The new Analytics tests compare past/current/future monthly evidence with the
existing summary service. Appearance tests compare financial rows and portfolio
values before and after customization; goal-source choices retain their native
identifiers, ordering and remaining reservation capacity.

## Working-tree validation

These measurements cover the full working tree, including earlier uncommitted
changes. They are not the test counts of the separately scoped commit; its
additional verification is recorded below.

| Check | Observed result |
|---|---|
| Complete isolated Django suite | 1,254 tests passed in 471.852 seconds under branch coverage; configured coverage was 95%, above the 70% gate. This run includes the final goal-source identity regression. Subsequent public-copy checks are recorded separately. |
| Goal and position identity follow-up | 66 focused tests passed after adding position identity to reservation-source choices. |
| Public-copy follow-up | 13 Pages tests passed after aligning the public Home description and Analytics label, including Brazilian Portuguese; the legacy `feature-reports` anchor remains. |
| Complete application browser run | 641 cases scheduled: initially 536 passed, 32 failed and 73 skipped. All 32 failures were resolved and rechecked: 31 passed together, then the remaining color-recovery case passed separately. No new skip or retry was introduced. |
| Final navigation and goal follow-up | A 35-case run covered the new Finance filter scenarios, goal-source identity, public copy and native period navigation. The 25 existing follow-up cases passed. After correcting three new fixture assumptions, all ten Finance scenarios passed together in 28.1 seconds, including the native GET case. |
| Guarded assistant browser coverage | 67 explicitly guarded synthetic-provider cases ran: 66 passed and one exposed a 0.000015px exact-geometry comparison. The corrected subpixel comparison and both streaming-tail cases passed in an eight-case follow-up. The fixture provider uses no credentials and blocks external server transports. |
| Python tooling suite | 44 tests passed. |
| JavaScript tooling suite | 26 tests passed. |
| Public preview capture | 32 synthetic 1440 × 1000 images generated across both languages and themes. |
| Public preview browser suite | 21 tests passed, including 320px layouts, compact labels, 44px targets, 10px minimum text, native fallback, history and legacy `#reports` ownership. |
| Preview capture tooling | Eight focused cases passed, including staged replacement/cleanup and inherited provider/private-vault isolation. These cases are part of the tooling coverage above. |
| Generated CSS | Rebuild and deterministic-output verification passed. |
| Documentation and source checks | Documentation links/anchors, JavaScript syntax, Ruff undefined-name checks and `git diff --check` passed. Translations contain no fuzzy or untranslated entries; compiled catalogue output was verified. |

Visual inspection covered representative rendered Home, financial analysis,
investment analysis and emoji holdings captures in both themes, plus English
and Portuguese phone emulation at 320px. Automated preview checks inspect all
eight views in both themes/languages. Browser validation used Chromium desktop
and phone emulation, including touch, real keyboard events and native forms;
it does not establish physical-device, Safari or Firefox behavior or complete
application accessibility.

The preview uses disposable synthetic profiles, a separate loopback server and
temporary storage. Its capture process explicitly clears inherited assistant
settings, disables real authorization/inference and binds its private directory
to disposable storage. It does not render an owner's financial records.

## Browser coverage and limits

Finance filters retain the monthly category/outlook scope and each independent
chart cursor through interleaved choices, pending requests, Back/Forward and
native GETs. Tests also cover Ctrl-click native tabs, a disappearing month-reset
control's focus, unavailable horizon bounds, unrelated help/composition and
aborting a held request when leaving the workspace. The accepted implementation
is the version exercised by the final ten-case run, not an earlier observation.

The ordinary suite's 73 skipped cases comprise 67 guarded assistant cases,
subsequently exercised with the synthetic provider, and six previously paused
statement/import-interface cases. Those six remain outside browser coverage;
their feature gates were not reopened by this delivery.

The initial failures retained old navigation counts, ambiguous period or
disclosure selectors, an offscreen geometry baseline, and the former color
palette/recovery behavior. Corrections retain the original ownership,
financial-value, focus, keyboard and geometry assertions. New Finance fixtures
wait for HTMX settlement before moving focus, select their synthetic category
explicitly and observe native tabs through the browser context. Native GET
assertions do not await JavaScript animation callbacks.

An exploratory assistant run incorrectly combined disabled-connection specs
with the guarded provider configuration. It was interrupted and excluded from
acceptance; only the seven explicitly guarded specs were then selected. That
exploratory run also observed one streaming Ctrl+Home timing race. It did not
recur in the supported 67-case run or the final streaming follow-up. No chat
runtime workaround or relaxed scroll-position assertion was introduced; the
observation remains useful during manual testing.

Commands used for application browser acceptance include `npm run test:e2e`,
`npm run test:e2e -- --last-failed`, focused runs of
`analytics-filter-islands.spec.js`, `planning-subareas.spec.js`,
`public-home.spec.js` and `departure-period-navigation.spec.js`, and the guarded
assistant selections described in [the test guide](../../tests/README.md).
Logs and synthetic application screenshots are retained under the ignored
`.local/analytics-investments-2026-10-20/` evidence directory.

## Separately scoped commit verification

The owner subsequently authorized a local commit of Analytics, investment
identity, documentation and preview. A source copy based on `cc110a8` contained
only that delta: earlier card/account controls, invoice credits, installment
openings and assistant action/Markdown changes were excluded. Shared compiled
CSS and translations were rebuilt from the scoped sources, and all 32 synthetic
preview captures were regenerated from that same copy.

| Check on the isolated commit candidate | Observed result |
|---|---|
| Django system and migration checks | No issues; no missing migration. |
| Complete Django suite | 1,039 tests passed in 139.364 seconds. |
| Focused application browser suite | 41 passed: both Analytics sections, independent filters, compatible legacy URLs, native/invalid emoji forms, goal references and six destinations in both languages/themes, including 320px. |
| Investment spacing follow-up | Six position-identity cases passed after keeping the shared 24px tab spacing within the investment selector, independently of earlier Planning changes. |
| Static preview suite | All 21 passed in 31.5 seconds after the final spacing capture and history-fixture correction. |
| Tooling | 44 Python tests and 16 JavaScript tests passed. |
| Documentation | 89 documents, 768 local references, no unresolved target. |
| Source and generated assets | Ruff F checks, translation compilation and scoped diff checks passed. |

The final preview follow-up corrected a test-navigation race: wait for the
requested workspace before opening its visible, theme-specific screenshot.
The Back/Forward, dialog dismissal and focus assertions were retained; no
preview runtime workaround or retry was introduced.

An inherited catalogue note names `static/js/assistant-markdown.js`, whose
implementation belongs to the earlier uncommitted assistant batch. This
scoped commit neither adds that resource nor certifies those earlier assistant
documentation claims.

The original working files and installation data remain in place. Only this
candidate's selected Git content enters the separate commit; the prior changes
remain available in the working tree. The regenerated public preview belongs to
this scoped delivery. Candidate evidence is under ignored
`.local/analytics-investments-2026-10-20/commit-scoping/`.

## Local migration and delivery boundaries

The additive `investments.0011_position_appearance` migration was rehearsed on a
copy before being applied to the local installation. A fresh private SQLite
backup with mode `0600` preceded the real migration. Preservation checks covered
48 pre-existing tables; private amounts, identifiers and backup paths are not
included in this tracked review. The change adds cosmetic metadata rather than
reinterpreting holdings, opening dates, operations or bank balances.
The final read-only SQLite integrity check passed, the appearance table is
present, and the private backup's hash and `0600` mode remain unchanged.

This delivery introduces no new financial calculations, AI-generated analyses,
external model calls, market feed or bank connection. Assistant changes only
recognize the new owned routes and validated filter context. Raw captures and
logs remain under ignored local output directories; committed preview images
contain synthetic data. The original implementation checkpoint made no commit;
the owner later authorized the separate local commit described above. Push,
merge, tagging, release and publication remain unauthorized and were not performed.
