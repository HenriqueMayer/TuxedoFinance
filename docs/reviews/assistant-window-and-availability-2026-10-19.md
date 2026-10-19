# Assistant window and connection availability — 2026-10-19

## Scope

The owner reported a locally selected ChatGPT account alongside a disconnected
composer, and requested recognizable window controls for the assistant.
This increment follows the existing uncommitted chat/effort work on
`feat/tuxedo-assistant-foundation`. The current contracts remain in the
[assistant guide](../apps/assistant.md),
[navigation guide](../frontend/navigation.md#assistant-panel) and
[interface map](../interface-map.md).

## Corrections

A saved local selection does not enable the installation's authorization or
inference settings. Account settings and the panel now distinguish those states
and explain the blocked capability without treating a retained account link as
an active message connection. Read-only status inspection remains external-call
free when either gate is off.

The installation's previous launch supplied the two switches only as process
variables. A normal restart omitted them, restoring the checked-in disabled
defaults. The owner's already-authorized connection/inference opt-ins now live
in the ignored local environment file. An ignored private backup was saved
before that narrow configuration edit. The checked-in defaults remain off;
fresh clones and isolated browser runners do not inherit this installation's
opt-in. No credentials were changed or reauthorized.

The assistant has a window titlebar with grouped 44px Minimize and Close
controls. Its approved mark and motion remain unchanged. Minimize retains the
current document's draft, model/effort choices and active reply behind a restore
tab. Restoring reauthorizes the same user and session before revealing content;
Close cancels a reply and discards temporary composer state without deleting
saved conversation history. Escape dismisses an open chat disclosure first and
then minimizes the window. The Design Lab mirrors these interactions with
synthetic messages and page-memory-only state.

Restoration also preserves a non-tail transcript position captured before the
window becomes hidden. If a streaming completion refreshes the hidden document
while an earlier restore GET is delayed, the newer authorized document wins.
Restoring never replaces it with an older incomplete response.

## Validation

The isolated assistant Django suite passed 198 tests, including all local
authorization/inference gate combinations, disabled request rejection without
provider calls or message writes, and opaque UI-session binding across login
changes. Django checks and migration consistency checks passed; no new schema
change was required for this increment. JavaScript unit checks passed 16 tests,
and executable-correctness lint passed for the assistant and changed settings
module. CSS and Brazilian Portuguese translations were rebuilt.

All 72 unique browser scenarios passed against frozen final assets: 11 window
cases, 26 guarded chat/streaming cases and 35 standard history/connection/Lab
cases. They use disposable databases and a synthetic provider; ordinary
connection checks keep real authorization and inference off. Initial interrupted
runs or mixed-asset refusals during implementation are not counted as successful
final runs.

Rendered and interaction coverage includes wide desktop, 390px/320px phones,
short-height screens, touch, both themes, Portuguese/English, 44px controls,
native fallback, IME and keyboard navigation. Focused regressions verify chat
draft/model/effort/consent preservation, exact non-tail reading position, delayed
restore versus completed streaming, cancellation without history deletion, and
rejection after logout, another user or a fresh login by the same user. Existing
financial forms retain their geometry, values and departure protection.

Browser commands:

```bash
npm run test:e2e -- --assistant-fixtures tests/e2e/assistant/window-controls.spec.js
npm run test:e2e -- --assistant-fixtures tests/e2e/assistant/chat-ux.spec.js tests/e2e/assistant/streaming.spec.js
npm run test:e2e -- tests/e2e/assistant/local-chat.spec.js tests/e2e/assistant/connections.spec.js tests/e2e/catalogue/assistant.spec.js
```

The installed local settings page was inspected through its existing browser
session: it showed Chat enabled and the authorized selected account. An empty
transaction form then showed the ready composer, grouped window controls and
minimized restore tab. This used only authorized GETs, including model catalogue
metadata; no financial form or chat message was submitted. Evidence and source
hashes remain ignored under `.local/runtime/assistant-window-20261019/` and
`.local/test-results/assistant-tabs-20261019/`. Documentation validation found 73
documents and 663 local references, with no unresolved links; final syntax and
diff checks passed.

Phone coverage uses browser viewport/touch emulation, not a physical handset's
operating-system keyboard. The complete application browser inventory was not
rerun for this assistant-only increment.

## Boundaries

No publication, paid API fallback, account reconnection or real generation call
is included in this UI/status increment. Financial calculations and stored
records are outside its change scope. Browser validation must use the disposable
executor and guarded synthetic provider rather than the owner's installation.
