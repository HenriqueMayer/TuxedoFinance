# Bank title bar and account hierarchy — 2026-10-21

## Scope and result

Refine the open institution after owner feedback on its bookmark, title-bar
interaction and weak boundaries between accounts. Current behavior belongs to
[the banking guide](../apps/banking.md#bank-overview-details-and-dynamic-consultation)
and the [interface map](../interface-map.md).

The institution miniature now replaces the bookmark in the open bank header.
The existing labelled Minimize anchor has a stretched native hit area contained
by that bar: the name, icon and empty bar space return to the overview. Account
content remains independent. There is one link and one keyboard stop; the
existing programmatic heading focus, HTMX scope, validated departure guard and
native GET destination remain. A translated title preserves the complete bank
name on pointer hover. The decorative frame is narrower on phones, while the
activation area remains the whole bar and the visible action stays at least
44px high.

Each account has a separate bordered surface and space before the next one.
A subtly contrasting header groups its name, currency and account actions.
Amounts, linked credit cards and the details/planning footer have distinct
reading areas. Card artwork, source links, menus and financial POSTs remain.
No financial model, migration, calculation or ledger service changed here.
Existing working changes were preserved; pre-task copies are under
`.local/bank-account-hierarchy-2026-10-21/before/`.

The Design Lab demonstrates two bounded accounts. Its narrow specimen keeps
complete monetary values readable. Four Banking preview images were refreshed
from disposable synthetic profiles; the other 28 captures were restored
byte-for-byte. This local capture does not publish the tour.

## Verification

- 21 isolated Django tests passed: account presentation, internal workspace,
  ownership, baseline financial values and workspace organization. The automatic
  Django system check found no issues.
- The initial targeted browser run passed 21 of 22 cases. One older bank-color
  assertion still inspected the overview link's retired outer border instead
  of its visible identity stripe. That assertion was updated, preserving the
  color workflow. A focused nine-case run then passed, including bank color
  creation/error recovery/editing and eight bilingual account layouts.
- Actual pointer input covers the bank name and an empty corner inside the
  title bar; account disclosure interaction does not minimize the bank. Real
  keyboard input covers the labelled action, focus restoration, section tabs,
  Back/Forward and unsaved inline redemption protection. Native mobile coverage
  activates the stretched title link without JavaScript.
- Application and catalogue layouts were inspected at 320px and desktop widths
  in both themes, including long institution/account names, two accounts,
  currencies and unchanged card artwork. EN/PT-BR cases exercise translated
  navigation and action labels.
- After compacting the phone header artwork and keeping narrow catalogue amounts
  on one line, the final 15-case run passed: eight desktop/320px theme/language
  cases, two unsaved-redemption guards, native mobile navigation and four Design
  Lab cases. This run also checks an actual empty title-bar corner.
- All 21 static preview tests and 26 dependency-free JavaScript tests passed.

CSS was rebuilt and compared byte-for-byte. The existing translation catalogue
passed format validation and a compiled-byte comparison. Documentation links,
changed JavaScript test syntax and `git diff --check` passed.

## Limits and evidence

These are focused presentation/navigation checks, not a new complete Django or
application-browser run. No live provider, bank connection, financial import or
installation database was used. No commit or publication was performed.
Logs, screenshots and source snapshots remain under
`.local/bank-account-hierarchy-2026-10-21/`.
