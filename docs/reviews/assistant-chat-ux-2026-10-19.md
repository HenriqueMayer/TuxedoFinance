# Assistant conversation layout — 2026-10-19

## Scope and observations

Unreleased interface work after `0235eae` on
`feat/tuxedo-assistant-foundation`. The owner requested a more recognizable chat
and confirmed Enter to send, with Shift+Enter for a new line. The existing
editorial palette, animated mark, fixed overlay and subscription connection
remain the starting point.

Fresh synthetic desktop/phone captures showed three problems: messages read as
ledger rows, the composer scrolled away with the conversation, and large form
controls left little space for reading. This lot changes presentation and chat
interaction, without changing financial calculations, provider selection,
per-request financial-context consent or stored conversation ownership.

## Changes

- User messages appear in restrained right-aligned bubbles; assistant text and
  its verified references stay on the left. The transcript scrolls independently
  above a persistent composer.
- History and conversation actions use deliberate native disclosures. Context
  remains a compact current-page link. Privacy copy is available inside History.
- The editor grows from one line to 120px, with native model selection,
  the initially unchecked Use page data control and labelled 44px Send/Stop
  actions below it. Enter sends; Shift+Enter adds a line; IME confirmation and
  blank Enter do not send. Native button validation remains available.
- Streaming follows the tail only while the reader is near it. Reading earlier
  messages preserves position, including the final authorized history refresh.
  Composer controls remain locked through that refresh so a new draft cannot
  be accepted and then overwritten by the replacement fragment.
- A demonstrated 390×320 failure placed Send below the visible sheet. The
  compact mode follows visual-viewport height below 400px, trims secondary
  chrome and caps the editor at 40px while retaining Context and editing actions.
  The native page retains document scrolling and mobile navigation clearance.
- The Design Lab demonstrates the same interaction with synthetic content.
  Current contracts live in the [navigation guide](../frontend/navigation.md#assistant-panel)
  and [assistant guide](../apps/assistant.md), rather than this dated record.

## Validation boundaries

Automated browser checks use the repository npm runner's disposable SQLite
database and loopback server. The guarded provider is synthetic, blocks external
transports and never reads the installation's linked account or private vault.
No automated test targets the owner's running server or financial database.

| Check | Current result |
|---|---|
| Assistant Django suite | 187 tests passed using isolated settings and data. |
| Streaming/chat browser suite | 19 tests passed against the final production assets, including long replies, scroll/focus preservation, delayed refresh, validation, cancellation and constrained-height controls. |
| Standard assistant and Lab browser suite | 28 tests passed against the final assets: 22 local chat/privacy/draft/native/touch cases and 6 catalogue cases. Together with the guarded suite, 47 scoped browser tests passed. |
| JavaScript unit checks | 16 passed. |
| Django configuration/schema | System check clean; no missing migrations. |
| Build/static checks | CSS rebuilt, PT-BR catalogue compiled, JavaScript syntax, focused Ruff, documentation links and diff whitespace checks passed. |

Reproducible browser commands:

```bash
npm run test:e2e -- --assistant-fixtures tests/e2e/assistant/chat-ux.spec.js tests/e2e/assistant/streaming.spec.js
npm run test:e2e -- tests/e2e/assistant/local-chat.spec.js tests/e2e/catalogue/assistant.spec.js
```

Rendered inspection covered light/dark desktop and phone layouts, English and
Brazilian Portuguese, long conversations/model labels, expanded disclosures,
invalid responses and no-JavaScript submission. Final short-height captures
show the textarea and Send/Stop inside 390×320 and 320×320 sheets; native Send
remains above the bottom navigation after ordinary keyboard/focus scrolling.

The native local server was restarted with its existing process environment;
the environment file, provider gates, vault location and database schema were
not changed. An already completed synthetic conversation was reopened through
an authorized GET to inspect the current interface. This did not generate a
new response or send financial context. Eligible model discovery remains the
existing account-bound operation.

Raw before/after screenshots stay in ignored local output under
`.local/runtime/assistant-chat-ux/`, including app, Lab, short-height failure
and native-page evidence. Versioned documentation contains no account
identifiers, financial rows, credentials or provider payloads.

## Remaining limits

Phone-sized viewports, touch emulation and constrained-height layouts provide
browser evidence; an operating-system software keyboard on a physical handset
was not inspected. The complete application browser inventory and live Docker
inference were not rerun for this interface-only lot. No model was called to
generate a new answer, no paid API was used, and no financial data was edited.
There is no migration, release, publication or provider expansion in this lot.
