# Home, Reports and Loyalty review — 2026-10-17

## Status and scope

Dated implementation and verification evidence for the working tree on
`feat/personal-finance-evolution`, including its existing unreleased changes.
This record does not authorize a release or establish later checkout results.
Current behavior belongs to the [frontend contract](../frontend.md),
[dashboard guide](../apps/dashboard.md), [banking guide](../apps/banking.md)
and [interface map](../interface-map.md).

The review compared fresh synthetic profiles with the approved
[Design Lab](../design-system.html), using desktop and emulated phone viewports,
English/Brazilian Portuguese and both themes. Browser writes used the official
disposable test runner. Personal databases, environment files, backups and
developer services were preserved.

## Reviewed steps and corrections

| Step | Surface | Result |
|---|---|---|
| 1 | Authenticated Home, category selection/composition, outstanding invoices, month navigation and outlook table | Keep full category names in a readable ledger column, separate exact values, provide at least 44px chart targets and contain long selected names. Outstanding invoices reuse the saved card miniature. The outlook table has a named, keyboard-focusable native scroll region. Existing destinations, return context and month-control positions remain intact. |
| 2 | Reports, four charts, period choices and source composition | Name and focus the three horizontally scrollable chart regions and explain horizontal scrolling on phones. Selected period shortcuts retain the same 44px target as links. Wrap full instrument identities in the ledger, bound SVG axis/tooltip captions while retaining full accessible identities, and keep help icons beside headings. Existing source links, filters and chart interactions remain intact. |
| 3 | Accounts subareas and loyalty registrations | Reuse the shared illustrated payment choices for linked cards, points-purchase funding, invoice awards, redemption/IOF destinations, transfer accounts, card accounts and invoice payment accounts. Saved colors/gradients and complete bank/account context remain visible. Multi-card choices retain native checkboxes and Space/Tab behavior. Filtering does not discard selection. Long summaries and bound errors fit the phone. |

The shared metadata widget uses each already-loaded model choice; it does not
issue a query per option. Conditional eligibility, ownership, native submitted
identifiers, existing server errors and complete no-JavaScript forms remain in
the owning forms. No model or migration was added by this review.

Financial services and chart calculations were not edited in this round.
SHA-256 comparisons of the protected financial sources remained unchanged.
On an exact backup of the same disposable synthetic database, all **44 report
point value labels** matched before and after. Presentation abbreviations do
not replace full record names in the ledger, accessible labels or source links.

## Verification

- **723 tests** passed in the complete Django discovery. Version consistency,
  Django system checks and the migration dry run passed.
- **31 distinct selected browser cases** passed through `npm run test:e2e`:
  five new Home cases, eight Reports cases, ten banking/loyalty cases and eight
  Home shortcut/shared-chart regressions. Focused reruns are not counted again.
  Coverage includes real keyboard events, both themes, desktop/phone widths,
  Portuguese labels, invalid responses, conditional choices, source returns,
  touch composition and native fallback without JavaScript.
- **19 Python tooling tests** and **16 JavaScript amount/allocation tests**
  passed. Ruff executable-correctness checks and `git diff --check` passed.
- The complete suite ran before the last Reports caption/heading refinements;
  the 17 focused Reports Django checks and the two affected browser cases were
  rerun after those final edits.
- CSS and Portuguese translation outputs were rebuilt and compared with their
  sources. Local documentation paths and anchors were checked.

The initial Home shortcut fixture used the São Paulo calendar while the test
application uses UTC. Its current-date fixture now follows the configured UTC
calendar; the application's date policy was not changed. Earlier failed
attempts were retained separately from accepted captures and passing reruns.

Before/after screenshots from this round were visually inspected; accepted
originals, logs and image hashes remain in the local review artifacts under
`/tmp/tuxedo-home-reports-loyalty-review/`. Those temporary artifacts are evidence,
not installation resources or durable documentation dependencies.

## Limits

The complete browser suite, physical phones, other browser engines, manual
screen-reader interoperability, release/Docker checks, dependency audits and a
new coverage percentage were not part of this round. Native keyboard/touch
checks and emulated phones provide bounded evidence, not accessibility or
physical-device certification. Full-page captures can place fixed navigation
at the captured viewport position; focused-control bounds were checked through
actual interactions. External documentation URLs were not fetched.
