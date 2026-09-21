# Planning evolution — implementation review

This review records the work on `feat/finance-planning-evolution` on 2026-09-20.
It records pre-release validation of the changes included in **v0.4.0**.
Release publication and image availability are tracked by the
[release workflow](versioning.md#container-releases).
No personal database was migrated, reset or populated during validation.
[FIN-11](https://hmayer.atlassian.net/browse/FIN-11) and
[FIN-12](https://hmayer.atlassian.net/browse/FIN-12) were updated with scope,
acceptance criteria and validation evidence, then moved to **Done**. Their
completion comments explicitly distinguish local implementation from release
publication.

## Delivered behavior

| Area | Result | Main reference |
|---|---|---|
| Financial availability | Monetary cash pots, persistent partial reserves and account exclusions share one calculation; negative balances and obligations remain visible. | [Banking](apps/banking.md#monthly-planning-availability) |
| Investment semantics | Purpose belongs to the product; positions are product/asset pairs. Actual yields and opening holdings remain separate from simulations. | [Investments](apps/investments.md#purpose-and-cash-planning) |
| FIN-11 | Opening positions and operation history protect asset deletion, including mixed bulk and Admin operations. Empty assets remain removable. | `investments/test_planning.py` |
| FIN-12 | Shared date parsing and controls respect DMY/MDY across domains; machine dates and filters remain ISO. | [Frontend contract](frontend.md#planning-workspaces-and-shared-presentation) |
| Planning | Explicit named private drafts, incomplete-input recovery, duplication, comparison and reviewed 12-month commitment snapshots. | [Planning](apps/sandbox.md) |
| Simulations | Decimal monthly/annual effective rates; monthly opening-balance yield followed by contributions/withdrawals; editable monthly overrides. | [Investment simulation](apps/sandbox.md#investment-simulation) |
| Interface | Five primary destinations, grouped bank tables, investment sections, category hierarchy/usage and secondary actions. | [Canonical catalogue](design-system.html#workspaces) |
| Operations | Private non-overwriting native key creation; distinct raw/spreadsheet CSV; incremental Docker upgrade, backup rehearsal and recovery. | [Docker](docker.md#update), [Security](../SECURITY.md) |

## Review findings resolved

The audit identified account balance queries repeated per displayed account,
opening investment holdings omitted from evolution, cash projections based on
economic amounts instead of actual cash legs, and projections beyond the fully
synchronized horizon. Balances now use grouped reads, points-funded deposits do
not debit bank cash, fees follow actual settlement, and forecast navigation stops
before an incomplete future month. Competence-based activity remains separate
from bank movement dates.

Planning originally discarded invalid repeated rows and retained no scenarios.
The new implementation preserves invalid/unequal inputs, stores valid values
canonically, and keeps explicit snapshot refresh separate from save. Stable
source/occurrence keys prevent duplicated expenses after due-date changes.
Snapshot capacity is explicitly bounded at 2,000 obligations, without truncation;
a regression covers a normal native POST with more than 1,000 form fields.

Old schema-reset instructions now describe their historical pre-release context.
Supported installations retain the migration chain. Before release, documentation distinguished published v0.3.0 installation
instructions from unreleased features; the v0.4.0 READMEs select the new release.
The visual catalogue loads the application's compiled CSS, removing a duplicate
Tailwind runtime/token definition and obsolete workspace recipes.
Both READMEs omit empty tutorial placeholders and link installation/update
instructions to the maintained technical guides.

## Initial implementation validation

All application/browser validation uses disposable databases and loopback servers.
The following checks were executed locally against the implementation:

- Django: **268 tests passed**; combined line/branch coverage **91%** using the
  existing repository measurement scope, which includes tests and migrations.
- Repository tools: **14 tests passed**; version consistency, Django system
  checks and migration drift checks passed.
- Ruff executable-correctness rules: passed. Python runtime and npm dependency
  audits reported no known vulnerabilities at the time of the run.
- CSS rebuilt; PT-BR catalog extracted and compiled with no untranslated/fuzzy
  messages and valid interpolation placeholders.
- Shared catalogue inspected in light/dark themes and at 390px; no horizontal
  page overflow in the inspected layouts.
- Application browser suite: **58 tests passed** in the final complete native
  run, including both themes, mobile layouts, keyboard interactions, invalid
  submissions, HTMX updates and no-JavaScript paths.
- Static preview: **5 tests passed**; all **14 synthetic screenshots** were
  regenerated in English and Brazilian Portuguese, including Planning.
- Docker browser validation: the full candidate run passed 54 of 58 cases and
  exposed three report-layout regressions and one scenario-test timing race.
  After correction, **all 6 affected/related cases passed** on the rebuilt final
  image, including help and no-JavaScript forecast navigation. The complete
  native suite above also passed after those fixes.

The initial implementation's local amd64 image is
`tuxedo-finance:review-20260920`, image ID
`sha256:fa153fdfd4b749c0ecea99ed55635274e6c041066ad0b41a2adeb7ffdfff1a88`.
It predates the presentation follow-up below and does not contain those UI
adjustments.

The Docker upgrade fixture seeds 16 financial/model tables in the published
v0.3.0 image, preserves its identifiers, records, ownership, native balances,
loyalty totals and FX evidence across the candidate migration, verifies additive
defaults, restores a candidate backup and recovers with the old image plus its
pre-migration backup. The lifecycle rehearsal passed locally. CI now executes
that same procedure for amd64 and arm64 before publishing a release.

Local Docker Engine is **26.1.5**, below the documented **28+** supported baseline.
The local lifecycle result proves the tested migration/restore behavior; it does
not establish Docker 28+ host validation or a remote CI pass. No release, image
push or production deployment is part of this checkout delivery.

## Presentation follow-up

The subsequent visual review restored restrained surface and metric cards to
separate charts, institutions, planning stages and results. Related tables and
rows share a card instead of nesting containers. The canonical catalogue and
the English/Portuguese static tour reflect this composition.

Each primary destination retains its direct link and exposes its options on
mouse hover. A separate disclosure supports keyboard, touch and native
no-JavaScript access. Secondary action menus use the same controller; financial
content accordions keep their existing behavior.

Explanatory copy now uses the shared question-mark help beside field labels,
chart headings and totals. Error messages, missing-rate warnings, scenario
status and decisions remain visible. Native help has a bounded mobile panel;
enhanced help preserves focus, dismisses appropriately and initializes after
HTMX or simulator updates.

Follow-up validation uses disposable installations: all **268 Django tests**,
system checks and the migration drift check passed. All **75 application browser
cases** passed across scoped runs, including the rerun of all 12 form cases
after updating the keyboard sequence for contextual help. Navigation regressions
cover Escape priority and selecting/touching help text within an open menu.
CSS was rebuilt and compared
with a fresh build; **1,006 PT-BR messages** compiled without fuzzy/untranslated
entries. All 14 tour images were regenerated and the **5 preview tests** passed.
The catalogue and representative screens were inspected in both themes and at
mobile widths. `git diff --check` passed. These UI changes have not been rebuilt
into the Docker image named above or published.

## Visual correction and asset delivery

The final visual review corrected a delivery defect in already-open tabs: HTMX
replaced page bodies while leaving the previous stylesheet in the document head.
Navigation consequently combined current markup with obsolete styles. CSS and
JavaScript URLs now use content digests from the files actually served by the
installation. A stale or legacy document refreshes once at its next GET
destination, preserving the query string. POST validation responses remain in
place and are never replayed. Current documents continue normal HTMX navigation.

The desktop shell now keeps each label and its single SVG disclosure aligned.
The five destinations retain direct navigation, hover options, keyboard and
native access. Shared typography, quieter secondary actions and restrained
surface/metric cards restore hierarchy across Banks, Categories, Transactions,
Investments, Reports, Settings and both planning workspaces. Mobile bank rows
show their metrics together; investment positions use readable summaries.
Repeated headings and oversized chart/empty regions were removed, without
changing financial calculations. Contextual help stays next to its subject.

Full-page review covered both themes at 1440px and 390px, including account
instruments, loyalty programs, long movement lists, invalid forms and incomplete
scenario comparisons. That review also found clipped category filters, split
currency/amount lines and crowded mobile actions; each was corrected and
recaptured. Form testing caught focus-dependent instructions moving buttons
between pointerdown and pointerup. Search guidance now remains accessible
without changing layout on blur; direct mouse clicks and keyboard actions are
both covered. Same-page navigation also restores scroll after HTMX settles
attributes, preventing mobile sorting from shifting the viewport after the
initial restoration; a user-selected focus is preserved.

The canonical catalogue uses the same compiled styles and demonstrates the
current shell, typography, cards, responsive account tables and editable
simulation sheet. Its desktop/mobile, theme, keyboard and native paths were
inspected. All 14 bilingual tour images were regenerated from disposable
synthetic data after the final visual changes.

Final verification for this correction:

- **277 Django tests** passed in the complete final run; system and migration
  checks passed. Repository tooling passed **14 tests**; version consistency,
  Ruff executable-correctness checks and `git diff --check` passed.
- All **82 application browser cases** passed across the complete run and
  subsequent scoped corrections. The complete run exposed the picker blur
  defect, a stale header selector and mobile post-settle scroll anchoring.
  All affected files were rerun; the final scroll/asset run passed **11/11**.
  A yield run interrupted by Docker network creation was repeated after cleanup
  and passed **2/2**, without suppressing browser errors.
- **5 static preview tests** passed. The final **14 screenshots** cover the
  current composition in English/Portuguese. CSS matches a clean compilation;
  **996 PT-BR messages** compile without fuzzy or untranslated active entries.
- The active development server's anonymous login was checked read-only: its
  stylesheet bytes match the checkout and its content-versioned URL. No owner
  session or financial data was used for that delivery check.

The updated local Docker image is `tuxedo-finance:ui-review-20260920`,
`sha256:6e1e95aa2e6fd7e3371fbe3f7c3725db8375f2d5188395ed28d7f6da472b8ef7`
(`linux/amd64`). The UI candidate passed **16/16 Docker browser cases** for
asset recovery, navigation, shell geometry and runtime delivery. After the final
scroll correction, the image was rebuilt and all **5 affected Docker cases**
passed: stale assets/invalid POSTs plus viewport and focus at 390px and 1280px.
Both runs removed their own containers, networks and volumes. The host remains
Docker Engine 26.1.5, below the documented 28+ baseline; this is local evidence,
not a remote CI or release-publication claim. The financial upgrade/restore
rehearsal above was not repeated for these presentation-only changes.

## Compatibility and remaining roadmap

The only schema changes add account planning fields, product purpose and private
scenario drafts. Existing accounts remain included, reserves start at zero and
products remain investments until the owner explicitly reclassifies them.
Prior migrations are unchanged.

Salary budgeting remains BRL; actual funding uses the configured reporting
currency. Missing FX produces an incomplete consolidated total rather than an
implicit conversion. Stored opening positions precede the recorded operation
history without assigning an invented historical acquisition date.

Market quotes, exchange price histories, agent integration and free-form formulas
remain outside this increment. No automatic tax, CDI, inflation or real-market
return is assumed by the investment simulator.

Operational reference contracts: [Django date widgets](https://docs.djangoproject.com/en/6.0/ref/forms/widgets/#dateinput),
[OWASP CSV injection limitations](https://community.owasp.org/attacks/CSV_Injection),
and [Compose recreation and wait semantics](https://docs.docker.com/reference/cli/docker/compose/up/).

## Release preparation validation

The complete final feature checkout passed 279 Django tests (91% combined
coverage), 14 tooling tests, all 86 native browser tests and 5 preview tests.
Python and npm dependency audits reported no known vulnerabilities. Version,
migration drift, Ruff and whitespace checks passed.

[PR #21](https://github.com/HenriqueMayer/TuxedoFinance/pull/21) passed native
amd64 and arm64 Docker validation, including all browser cases, upgrade from
v0.3.0 and backup/recovery. Its first native CI attempt had an intermittent
touch-help assertion failure; the unchanged full job passed on the second
attempt, and the affected test passed 10 additional local repetitions. No test
assertions were removed or relaxed.

The release PR exposed a separate timing race in the bank viewport assertion:
it sampled the position after focus restoration but before HTMX's final settle
and animation-frame restoration. The assertion now polls for completion while
retaining the same less-than-four-pixel tolerance and keyboard interaction.
The mobile help test now captures the actual viewport after completing its
touch sequence, avoiding full-page screenshot viewport changes between taps.
It retains the open/close, outside-tap, content and viewport-bound assertions.
