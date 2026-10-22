# Assistant model and reasoning settings — 2026-10-19

## Scope and delivered behavior

This increment follows the uncommitted
[chat polish](assistant-polish-2026-10-19.md) on
`feat/tuxedo-assistant-foundation`. The owner requested optional reasoning effort
and a smaller configuration surface. Earlier working changes remain present;
this increment does not authorize publication or a paid API route.

The composer now keeps Model and Reasoning effort inside one deliberate native
Chat settings disclosure. A compact caption preserves the current selection;
the transcript and workspace keep their dimensions. The settings surface opens
above the editor, scrolls internally in short viewports, and preserves 44px
activation areas. Escape dismisses settings before the chat; Tab-away and
outside clicks dismiss it. Server-invalid configuration opens for recovery.
The native page remains usable without JavaScript.

The authenticated account catalogue supplies model-specific capabilities.
Recognized effort values are retained as bounded metadata; unadvertised levels
are never inferred from a model name. Model default omits `reasoning` from the
provider request. Explicit levels produce `reasoning: {effort: value}` only after
form and service validation. An incompatible deliberate model change resets the
effort to Model default and announces that change. Server submissions still
reject incompatible pairs. Completion refreshes preserve both choices.

The additive `assistant.0004_generationrun_reasoning_effort` migration records
the choice on the generation run and includes it in replay-conflict checks.
Existing runs retain the empty, provider-default value. No financial schema,
calculation, context-consent rule or provider authentication flow changed.

Current contracts remain in the [assistant guide](../apps/assistant.md),
[navigation guide](../frontend/navigation.md#assistant-panel) and
[interface map](../interface-map.md). The Design Lab demonstrates the same
configuration using synthetic models and replies.

## Verification

All automated browser and Django checks use disposable data. The guarded
provider and account catalogue contain synthetic capabilities and do not access
external inference or installation credentials.

- The complete assistant Django suite passed: 194 tests, including capability
  filtering, payload omission/defaults, explicit effort, invalid pairs,
  idempotency conflicts and native request recovery. Django system checks and
  migration consistency checks were clean.
- JavaScript unit checks passed: 16 tests. CSS and Brazilian Portuguese
  translations were rebuilt. Syntax, documentation links and diff checks were
  checked independently.
- All 61 unique scoped browser scenarios passed across the guarded chat,
  streaming, local history, connection and Design Lab specs. The guarded set
  passed 26/26. After the final reset-notice adjustment, its six affected
  configuration cases passed again. The standard set passed 34/35 in one run;
  the remaining case encountered the expected asset-revision refusal while a
  JavaScript edit was being saved. That case and all six Lab cases passed again
  with frozen final assets. An earlier concurrent standard run was terminated
  before completion and is not counted as a successful full run.
- Rendered inspection covered desktop 1440px, phone 390px, narrow 320px and
  constrained 320px-height surfaces, light/dark themes, translated Portuguese
  settings, long model names, native keyboard choices, error recovery,
  explicit/default effort, outside/Tab/Escape dismissal and completion refresh.
  The final screenshots show bounded controls and no composer growth from
  opening settings. The reset notice clears after a deliberate valid choice.
- Executable-correctness lint passed for the assistant package. Documentation
  validation found 72 documents, 658 local references and no unresolved links.

Commands:

```bash
npm run test:e2e -- --assistant-fixtures tests/e2e/assistant/chat-ux.spec.js tests/e2e/assistant/streaming.spec.js
npm run test:e2e -- tests/e2e/assistant/local-chat.spec.js tests/e2e/assistant/connections.spec.js tests/e2e/catalogue/assistant.spec.js
```

The first browser pass exposed a narrow-screen intrinsic sizing issue with a
long model caption. A bounded grid track fixed the overflow; the final pass
retains that case. Independent review also identified clicks on non-focusable
workspace surfaces as a dismissal gap; the settings handler now covers them.

## Installation and evidence boundaries

The existing loopback development server was restarted with its original
environment. Before applying migration 0004, SQLite's backup API saved a local
private backup under ignored `.local/backups/assistant-effort-20261019/`.
Every pre-existing table retained its row count; only the migration ledger gained
its expected entry. Existing generation runs retained the empty effort value.
Financial records, the environment file and credential vault were preserved.

A new authenticated native chat tab verified the real account catalogue,
translated settings and an available explicit effort selection. It created no
conversation or message, submitted no financial form, and made no generation
request. This verifies catalogue availability and local presentation, not a new
live inference result. Provider payload behavior was tested through the guarded
transport.

Ignored artifacts live under `.local/runtime/assistant-effort-20261019/` and
`.local/test-results/assistant-effort-20261019/`, including the migration
comparison, source hashes, native screenshot and scoped browser captures.
Phone inspection uses Chromium viewport/touch emulation and constrained-height
screens; a physical handset's operating-system keyboard was not tested.
The full application browser suite was not rerun for this scoped assistant
increment. No commit, publication, release or paid API use is included.
