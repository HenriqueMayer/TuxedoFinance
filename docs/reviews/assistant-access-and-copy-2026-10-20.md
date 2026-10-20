# Assistant application access and Markdown copy — 2026-10-20

## Scope and observed cause

Focused working-tree delivery based on `aac5891`, following the owner's chat
feedback. The latest saved application conversation was inspected read-only.
It showed page-only orientation, insufficient financial evidence and no monthly
calculation tool. The prior four-action toolkit could prepare records, but could
not consult another workspace or run the existing salary planner. This review
does not embed the private transcript or installation records.

The owner requested default access to their saved application data, automatic
read/calculation execution, clarification only for material ambiguity and
explicit confirmation for persistent changes. Publication and Open Finance
remain paused. Existing uncommitted work was preserved.

## Delivery

- Conversation options now offers Copy conversation as Markdown; each message
  has a copy action. Authenticated exports include complete raw history beyond
  the display limit, verified references and reviewed action state. Native links
  download `.md`. Enhanced copying reauthorizes the same owner/session after the
  body finishes; denied clipboard access offers a deliberate download fallback.
- The assistant can read twelve owned financial areas independently of the
  visible page. Context remains a compact orientation badge. The page-data
  checkbox was removed from the app and Design Lab. Initial requests advertise
  tools rather than copying the entire database; relevant evidence is fetched
  only as needed, with cutoff/currency/missing-data and truncation metadata.
- Monthly CLT scenarios reuse the ordinary form, payroll calculation and
  economic commitment snapshot. Other payroll deductions, additional expenses
  and category reductions remain separate. Category cuts reconcile canonical
  split/installment/FX cents, reject overlaps/excess and change only the scenario.
  Missing FX or unsafe legacy IOF mapping does not become a fabricated remainder.
- Transaction editing/deletion now has immutable before/after or deletion
  review, with fresh server validation and separate confirmation. Omitted edit
  fields preserve source values exactly. Existing split/generated locks,
  recurrence repairs and accounting synchronization rules remain authoritative.
- Instructions `v5` direct actual read/calculation tool use and supersede older
  page-only capability claims in conversation history. Earlier versions remain
  explicitly loadable. Up to nineteen completed turns accompany the question.
  The bounded provider loop now supports five responses/ten tool calls within
  its existing 90 seconds; there is no automatic retry or paid fallback.

Current contracts: [consultations](../assistant/consultation.md),
[confirmed actions](../assistant/actions.md) and [assistant guide](../apps/assistant.md).

## Validation evidence

All automated application/browser fixtures used disposable databases, isolated
environment settings and loopback servers. No model, OAuth, banking request or
new financial export to a provider was performed.

| Responsibility | Result and evidence |
|---|---|
| Complete Django suite | 1,150 passed on the final Python code in the documented disposable environment. System checks and migration-drift checks passed; no new migrations detected. |
| Copy/window/chat UX | 43 browser cases passed: 9 copy/export, 22 chat UX and 12 window/session cases. |
| Action/consultation/Markdown/catalogue/Planning | Initial 32-case batch: 28 passed; four old assertions incorrectly counted deliberate copy/download links as model Markdown links. The renderer-only assertion was corrected. |
| Focused final browser rerun | All 7 passed: 5 Markdown/progress cases and both cross-workspace cases, extended to category cuts, in desktop/light/EN and phone/dark/PT. This completes 75 distinct affected browser cases. |
| Canonical simulations | 23 focused calculation tests plus dispatcher and Sandbox regression checks, including read-only SQL guards, payroll-versus-expense meaning, FX gaps, splits/installments, points/IOF, category families, cent reconciliation and rejected cuts. |
| Consultations | 21 focused tests cover all twelve areas, malformed ownership, selected records, bounded Unicode results and no preference/financial writes. |
| Confirmed edits/deletion | 20 new service tests plus existing action-service regressions cover omitted fields, stale/foreign records, repeated confirmations, ledger rollback, locked sources and legacy recurrence repair. |
| Export/actions HTTP | 17 focused cases passed, including complete history, owner/session isolation, no provider resolution and native downloads. |
| Repository/frontend | 23 JavaScript and 44 repository tooling tests passed. Ruff, syntax checks, CSS/gettext reproducibility and `git diff --check` passed. Documentation checker: 84 documents, 727 local references, zero unresolved. |

Screenshots were inspected on desktop and phones in both themes, including copy
feedback/options, raw/partial messages, denied clipboard fallback, conversation
scrolling, composer/settings, review controls and cross-workspace calculations.
Real keyboard tests preserve 44px targets, focus/drafts, Enter/Shift+Enter,
minimize/restore, logout/account changes and native forms/downloads. Clipboard
writes were mocked in browser fixtures to avoid changing the workstation's
clipboard; authentication, HTTP export, navigation and downloads were real.

Raw screenshots/logs belong under ignored
`.local/reviews/assistant-access-2026-10-20/`: `browser-copy-window`,
`browser-consultation-first`, `browser-final-consultation-markdown` and final
isolated Django logs. These are local validation artifacts, not public data.

## Preservation and limits

The installation database, `.env`, vault and original chat were not modified by
this delivery. The prior additive action-review migration was already applied;
this change needs no additional schema migration. Financial writes occurred only
in disposable fixtures after explicit test confirmation. No commit, merge, tag
or publication was performed.

The implemented payroll rule set retains its existing provenance/year; no tax
formula was replaced or inferred from live internet data. Simulations do not
add hypothetical salary to real balances or refund recorded expenses. Stored
projection freshness and missing data remain explicit. Offline/synthetic results
do not establish that a live model will choose tools correctly or comply with
instructions. No live subscription call was used for this validation. Browser
coverage is focused on affected responsibilities rather than the entire app.
