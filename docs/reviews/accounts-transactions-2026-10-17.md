# Accounts and Transactions review — 2026-10-17

## Status and scope

Dated implementation and verification evidence for the working tree on
`feat/personal-finance-evolution`, including its existing unreleased changes.
This record does not establish the status of a later checkout or authorize a
release. Current obligations remain in the [frontend guide](../frontend.md),
[interface map](../interface-map.md) and [contributor contract](../../AGENTS.md).

The review used fresh synthetic profiles, the approved [Design Lab](../design-system.html)
and desktop/phone viewports in both themes. Browser writes used the official
isolated runner; the installation database, environment and backups were not
used. Existing working changes and paused-feature gates were preserved.

## Reviewed steps and corrections

| Step | Reviewed surface | Outcome |
|---|---|---|
| 1 | Accounts, internal bank workspace, cards and complete banking registrations | Reuse compact native fieldsets and the shared responsive entry sheet. Keep long names inside account/card rows, ordinary choices, confirmations and activity. Bound the sticky bank title to two visual lines while retaining its full accessible name. Preserve markers, card colors/gradients, the angle dial and Minimize. |
| 2 | Invoice overview/history, confirmed payments and exchange rates | Give the phone's month criterion a full 44px row, with Bank/Status aligned below; keep FX controls aligned when a neighbouring field gains an error. Preserve filtered origins through payment/source editors and confirmations. Cancel and protected deletion retain the origin; deleting the bank itself returns to the surviving overview. FX keeps eight-place rates and its own list fallback. |
| 3 | Transaction list/create/edit/split/delete and category list/forms/import/delete | Wrap long names and shared notices/results without widening the phone. Preserve category search/type/level through import, deletion, Cancel and invalid responses. Verify persistent payment miniatures, three installments, exact-cent allocation limits and 60.00/40.00 recovery after a date error. |
| 4 | Documentation and agent instructions | Align English/PT READMEs and current guides, index sources by responsibility, separate dated validation history, clarify paused interfaces and replace fragile check/extraction recipes with isolated temporary-directory examples. Preserve keyboard, privacy, ownership and native-fallback contracts. |

Reward-redemption source editing exposed another return-context gap: the
inline editor discarded the report origin during its redirect. It now retains
only a validated explicit origin through GET, bound errors, Cancel and Save.
Without one, it still returns to the receiving bank, including a newly selected
bank after editing. Real browser tests cover report Cancel/Back/Save; Django
checks cover invalid and foreign origins and ownership.

Financial services, model fields, migration compatibility, native amounts,
classification/settlement rules and precision were retained. Styling and return
context do not create additional movements, payments or category allocations.
See the owning [banking](../apps/banking.md), [transactions](../apps/transactions.md)
and [categories](../apps/categories.md) guides for their current rules.

## Documentation organization

The [documentation index](../README.md) maps current guides to their owner.
[Contributing](../../CONTRIBUTING.md) owns executable development instructions;
`AGENTS.md` provides the implementation checklist and links the detailed
contracts. The [review index](README.md) separates historical observations from
current requirements.

Earlier validation sections were preserved in
[branch validation history](branch-validation-history.md) and the
[interface adoption record](interface-adoption-2026-10-17.md). Previously released
changelog entries were retained; overlapping unreleased interface iterations
were consolidated around the resulting behavior. Local credentials and private
`.codex` notes were excluded from published-guide checks and copying.

## Verification

- The final complete Django discovery passed **715 tests**. Version consistency,
  Django system checks and the migration dry run passed; no new migration was
  required by this review.
- **34 distinct selected browser cases** passed through `npm run test:e2e`:
  27 banking/card/loyalty cases and seven transaction/category cases. Focused
  reruns replaced earlier failed attempts; repeated runs are not counted again.
  Coverage includes English/PT, both themes, desktop/phone layouts, keyboard,
  touch on the gradient dial, invalid recovery, contextual returns and native
  GET/POST paths without JavaScript.
- **19 Python tooling tests** and **16 JavaScript amount/allocation tests** passed.
  Ruff's configured executable-correctness rules and `git diff --check` passed.
- Compiled CSS and Portuguese translations reproduce byte for byte from their
  sources. Active untranslated/fuzzy entries were absent and gettext format
  validation passed.
- Relative documentation paths, anchors and images, Design Lab references,
  README command/link parity and contributor command syntax were checked.
  Temporary-directory examples were also executed with mocked subprocesses to
  verify environment isolation and cleanup; this did not access personal data.

Current-run screenshots were saved and inspected before acceptance, with
before/after comparisons and original-byte manifests in the local visual
report. Raw captures and temporary logs remain outside the source and runtime
data directories. They are audit evidence, not installation instructions.

## Limits

The complete browser suite, physical phones, other browser engines, manual
screen-reader interoperability, Docker/release checks, dependency audits and a
new coverage percentage were not part of this round. Documentation checks did
not fetch external HTTP links. Phone viewports and touch emulation provide
bounded browser evidence rather than physical-device or accessibility
certification. Full-page captures can place fixed bars at the captured viewport
position; focused-control bounds and viewport captures were checked separately.
