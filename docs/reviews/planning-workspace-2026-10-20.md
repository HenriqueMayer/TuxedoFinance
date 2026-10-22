# Planning workspace reimagining — 2026-10-20

This review records the local Planning presentation change after `822de2f`.
Current behavior belongs to the [Planning guide](../apps/planning.md),
[simulation guide](../apps/sandbox.md), [workspace guide](../frontend/workspaces.md)
and [interface map](../interface-map.md). Earlier unrelated working changes were
retained. The implementation measurements below cover the working tree;
additional verification of the separately scoped commit appears later.

## Resulting behavior

- Replace This month / Goals / Tools with This month / Goals / Simulations /
  Alerts. Keep the principal rail at workspace width, including simulation forms
  and draft deletion. Native links retain active-page ownership, 44px targets,
  horizontal overflow and 24px separation from the content.
- Give Simulations its own Salary / Yield / Saved drafts navigation. Reopened,
  compared and deleted drafts belong to Saved drafts. The salary page is named
  Salary simulation; the alert page is named Local alerts. The assistant's
  existing sandbox context label follows Simulations.
- Preserve `/planning/tools/` as a local redirect to `/sandbox/`, including
  encoded and repeated query values. Existing budget bookmarks still return to
  the selected month and budget anchor. Editors retain validated Save/Cancel
  origins and simulations retain unsaved-work confirmation.
- Keep availability and category limits together in the monthly view. Separate
  the selected period from its explanation, retain recorded/projected and
  completeness notices, and show the existing number of limits discreetly.
- Present goals in a divided list, with backed progress, native currency and
  deadline columns. Phones stack the same values with visible labels. Long
  names, archived status, shortfalls and missing-FX warnings remain visible.
  Filtered empty results have their own explanation and the shorter Filters
  trigger fits the stable phone consultation rail.
- Align the bilingual READMEs, current guides, Design Lab and static preview.
  Refresh only the four public Planning captures from disposable synthetic
  profiles, preserving the other preview views and existing public anchors.

This delivery introduces no financial metric, goal icon preference, schema,
reservation, posting, bank connection or provider call. Monthly cash, category
spending, goal backing, CLT and yield calculations retain their existing services.
The pre-existing financial-service changes were byte-identical to the recorded
pre-task snapshot. No installation database or environment file was changed.

## Implementation validation

| Check | Observed result |
|---|---|
| Django system and migration checks | No system issues and no missing migration. |
| Planning, Sandbox and assistant-context suite | 114 tests passed in the final run, in 13.727 seconds, with temporary storage and an empty environment file. |
| Main browser run | 95 cases scheduled: 84 passed, nine failed and two existing paused-import cases were skipped. All nine failures were corrected and rechecked below; no new skip or retry was added. |
| Correction and presentation follow-up | 23 passed in 1.4 minutes: section ownership, native navigation, touch geometry, long names, goal filters/progress, both tax scenarios and the Design Lab. |
| Final naming and help follow-up | 15 passed in 29.1 seconds: both languages/themes, desktop/320px navigation, draft context, pointer/keyboard/touch/native help and the salary calculation screen. |
| Design Lab anchor follow-up | Four passed in 3.5 seconds after keeping the linked goal heading below the sticky catalogue header, in both themes at 1440px and 320px. |
| Static preview | 21 passed in 33.8 seconds, including native fallback, history, themes and narrow layouts. |
| JavaScript tooling | 26 tests passed. |
| Source and generated assets | Ruff F checks, deterministic CSS output, gettext format/compilation checks and `git diff --check` passed. No fuzzy or untranslated entries remain. |
| Documentation | Local paths and anchors passed `scripts/check_docs.py`. |

The first browser run found undersized short English section labels and a
partially clipped Portuguese link at 320px. Minimum widths and compact phone
gaps keep the native rail usable. Two existing reservation tests still expected
the old cofrinho label without its investment emoji; they now compare the full
selected native option while retaining the owned source-ID assertion. The ninth
failure was a fixture race: a tax table already visible from consultation did not
prove that the subsequent calculation had replaced the form. The fixture now
waits for that new result before editing salary. Financial output assertions
were retained and no calculation/runtime workaround was introduced.

## Inspection and limits

Rendered inspection covered monthly planning and divided goals on desktop and
phone emulation, English and Brazilian Portuguese, light and dark themes, long
unbroken names, filter clearing and empty matches. It also covered the final
Planning preview and linked Design Lab goal/simulation specimens. Browser tests
exercise real keyboard events, native submissions, invalid forms, reservations,
saved scenarios, Back/Forward and departure confirmation.

The browser runner owns its loopback server and disposable database. Preview
capture separately owns synthetic profiles and temporary storage, with real
assistant authorization and inference disabled. No test used an owner's server,
credentials, bank connection or live financial records. Evidence and preservation
snapshots are under ignored `.local/planning-reimagining-2026-10-20/`.

These are focused Chromium and phone-emulation checks, not a new complete
repository browser run, physical-device/Safari/Firefox certification or a full
accessibility audit. The two paused import cases remain unexercised. The
implementation checkpoint made no commit. The owner later authorized the
separate local commit described below; no push, merge, tag, release or
publication was performed.


## Separately scoped commit verification

The commit candidate starts at `822de2f` and includes only Planning, its related
navigation/test consumers, documentation and preview. Earlier account/card
controls, invoice credits, installment openings and assistant actions remain
outside the commit. Shared CSS and the Portuguese catalogue were rebuilt from
these scoped sources. All captures were generated in disposable storage; only
the four Planning images enter this commit, and the other preview images retain
their previous content.

| Check on the isolated candidate | Observed result |
|---|---|
| Django system and migration checks | No issues; no missing migration. |
| Complete Django suite | 1,043 passed in 199.954 seconds. |
| Related application/catalogue browser suite | 99 cases scheduled: 97 passed in 7.4 minutes, two existing paused-import cases skipped; no retry or new skip. |
| Static preview browser suite | 21 passed in 38.1 seconds. |
| Tooling | 44 Python tests and 16 JavaScript tests passed. |
| Documentation | 90 documents, 781 local references, no unresolved target. |
| Generated assets and source | Scoped CSS/catalogue outputs match their sources; translation format checks, Ruff F and scoped diff checks passed. |

The first complete candidate run exposed four stale expectations in three
existing test files: two demo-language cases still expected Tools to return
200, a localization case expected the former alert heading, and the investment
navigation case expected a Tools link. The demo now follows only that deliberate
legacy redirect and asserts its exact destination and month. The other cases
assert the new title and direct simulation destination. The full 1,043-test rerun
then passed without changing runtime calculations or weakening financial and
ownership assertions.

Candidate evidence is under ignored
`.local/planning-reimagining-2026-10-20/commit-scoping/`. Original working files,
installation data and pending changes remain in place. The actual index receives
only the separately reviewed candidate content for the authorized local commit.
