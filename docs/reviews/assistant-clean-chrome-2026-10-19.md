# Assistant compact chrome — 2026-10-19

## Scope

The owner requested a cleaner, more compact assistant window after approving its
grouped Minimize/Close behavior. This presentation increment follows the existing
uncommitted assistant work on `feat/tuxedo-assistant-foundation`.
Current contracts remain in the
[assistant guide](../apps/assistant.md),
[navigation guide](../frontend/navigation.md#assistant-panel) and
[interface map](../interface-map.md).

## Presentation changes

The titlebar retains the approved cat/orbit artwork and its motion, with quiet
paired window controls instead of individually outlined buttons. Its local-history
subtitle remains available to assistive technology. One compact toolbar combines
History, the authorized Context destination and deliberate New/Delete actions;
Context keeps its accessible label without a separate visible label or row.

Messages use compact readable type and restrained spacing, with right-aligned
user bubbles and plain assistant text. Assistant-role labels remain accessible
without repeating the name before every answer. The shallow composer keeps
native Model/Reasoning effort settings behind its gear and uses a single-line
selection caption. A focused composer reveals the keyboard hint without moving
the transcript. The restored/minimized window uses the same quiet controls.

All interaction targets remain at least 44px. Presentation changes preserve the
existing streaming, cancellation, native submission, history, authorized restore,
draft retention, per-request context consent and provider boundaries.

## Validation

Fresh checks against the final assets passed:

| Check | Result |
|---|---|
| Guarded assistant browser scenarios | 37 passed: compact geometry, keyboard/model/effort recovery, streaming, cancellation, window restore and session isolation. |
| Local chat and connection browser scenarios | 29 passed: English/Portuguese, both themes, native submissions, connection states, history/deletion, HTMX and private navigation. |
| Design Lab browser scenarios | 6 passed: synthetic interactions, desktop/phone, touch, short viewport, reduced motion and native fallback. |
| Isolated Django assistant suite | 198 passed. |
| Django checks and migration drift | No system issues; no changes detected. |
| Frontend tooling unit tests | 16 passed. |
| Documentation links | 74 documents, 667 local references, no unresolved links. |
| Changed Python test correctness lint and whitespace | Passed. |

The 72 browser scenarios use `npm run test:e2e` with disposable databases and
loopback services. No developer database/server is used by the runner. Rendered
inspection covers empty/populated conversations, long replies and settings in
both themes, with desktop and 390px/320px phone layouts. Regression assertions
retain at least 44px activation targets and the 28px cat/48px orbit. They bound
the titlebar to 58px, the single toolbar to 46px, and the resting ready-composer
frame to 100px; the intended CSS dimensions are 56px, 44px and 98px respectively.
The first integrated run caught shared icon styles restoring button outlines;
chat-scoped overrides now preserve quiet controls and 14px action glyphs. The
context-link Django assertion now compares semantic HTML, including its full
translated title, without depending on attribute order.

Browser commands:

```bash
npm run test:e2e -- --assistant-fixtures tests/e2e/assistant/chat-ux.spec.js tests/e2e/assistant/streaming.spec.js tests/e2e/assistant/window-controls.spec.js --output=.local/test-results/assistant-clean-20261019/guarded-final
npm run test:e2e -- tests/e2e/assistant/local-chat.spec.js tests/e2e/assistant/connections.spec.js --output=.local/test-results/assistant-clean-20261019/standard-final
npm run test:e2e -- tests/e2e/catalogue/assistant.spec.js --output=.local/test-results/assistant-clean-lab-verified
```

Ignored local evidence lives under
`.local/test-results/assistant-clean-20261019/{guarded-final,standard-final}`
and `.local/test-results/assistant-clean-lab-verified/`. Presentation fingerprints
and the supplied reference are under
`.local/runtime/assistant-clean-20261019/`. Committed CSS was rebuilt from source;
current UI copy retains its existing English/Portuguese translations.

## Boundaries

No model call, financial calculation, database/schema change, account
reconnection, paid API route or publication belongs to this presentation scope.
Browser validation uses disposable installations and synthetic providers. Phone
viewport/touch emulation does not establish physical handset keyboard behavior.
The full financial-application browser suite was not rerun for this presentation
increment. No commit or publication was made.
