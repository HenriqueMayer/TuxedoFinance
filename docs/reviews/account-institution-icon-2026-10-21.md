# Account institution icon — 2026-10-21

## Initial placement

Account headers initially reused the shared institution icon and neutral account-choice
artwork (54 × 36px, 23px glyph). The decorative miniature sits beside the full
account name and native currency, including inside reserves and refreshed
account fragments. It adds no link, control or keyboard stop. Existing card
artwork, institution markers, actions and financial values remain unchanged.

The banking guide and Design Lab show the same identity. The four synthetic
Banking preview captures were refreshed; the other 28 captures were restored
byte-for-byte. No models, migrations, financial services or installation data
were changed. Existing uncommitted work was preserved.

## Verification

- 13 focused isolated Django tests passed: account presentation and workspace
  organization, including existing amounts, ownership and participation flows.
- 17 isolated browser cases passed: 320–1440px, both themes and languages,
  long names, artwork dimensions, keyboard actions, invoice recovery, native
  submissions without JavaScript and the Design Lab.
- Two phone presentation cases were repeated for close-up visual evidence of
  the account header in Portuguese, in both themes.
- Rendered desktop preview and phone account headers were visually inspected
  in both themes. The icon keeps its proportions and the name wraps beside it.
- CSS was rebuilt and compared byte-for-byte; documentation links, JavaScript
  syntax and `git diff --check` passed. No new translated copy was introduced.

Logs, screenshots and the pre-task source snapshot are under
`.local/account-institution-icon-2026-10-21/`. Browser and preview runs owned
disposable databases and loopback servers, with real providers disabled.
No publication or commit was performed. This focused cosmetic validation does
not establish a fresh full-application browser or Django suite result.

## Placement correction after owner review

The owner clarified that the intended location is the **Your banks** institution
index, beside Banco Inter, Mercado Pago and Nubank, rather than nested account
headers. The miniature was moved to that bank-link identity, retaining its
neutral artwork, bank-color marker, full name, account/card counts and arrow.
The originally added account-header miniature was removed. There are no new
controls, destinations, financial calculations or data changes.

Current canonical documentation, the Design Lab specimen and regression
assertions reflect this placement. The intermediate Banking screenshots were
restored to their pre-icon versions: the public tour opens the bank's internal
workspace, which no longer contains the misplaced account icon.

The correction passed 13 isolated Django tests and 12 isolated browser cases
(desktop/320px, both themes/languages, real keyboard navigation and catalogue
anchors). Bank-link close-ups were visually inspected in both themes. CSS
rebuild comparison, source syntax, documentation links and diff checks passed.
These checks use disposable data; no publication or commit was performed.
