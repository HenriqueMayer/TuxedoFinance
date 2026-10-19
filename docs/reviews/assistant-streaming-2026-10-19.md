# ChatGPT-plan streaming — 2026-10-19

## Scope

Unreleased work after `94953c8` on `feat/tuxedo-assistant-foundation`.
This lot adds selected-account model discovery, explicit model selection,
progressive text responses, cancellation and local generation history. It also
aligns linked-account actions with the existing shared buttons. Authorization
and inference remain separate, default-off gates. There is no API-key billing,
automatic retry, account/model fallback, financial execution or publication.

The owning specification is the [assistant guide](../apps/assistant.md).
Earlier [native sign-in evidence](assistant-native-sign-in-2026-10-19.md)
retains its original limits.

## Local validation

All automated checks used disposable data. Browser checks ran through the npm
runner, with its owned database and loopback server. Standard browser runs kept
both provider gates off. The dedicated streaming run used guarded test settings,
synthetic connections/models and responses, and blocked external networking.

| Check | Evidence |
|---|---|
| Complete Django suite | 927 tests passed before the final transport-compatibility adjustments; subsequent focused checks cover that adapter. |
| Assistant regressions | All 187 tests passed after the final MIME compatibility and SQLite cancellation-order fixes, including 30 provider tests. The tightened blocked-stream cancellation regression also passed 30 independent repetitions. |
| Standard assistant browser coverage | 29 tests passed: responsive overlay, both themes/languages, keyboard/touch, history/privacy, financial drafts and native fallback. |
| Streaming browser coverage | 6 tests passed: desktop/phone, both themes, English/Portuguese, model keyboard selection, per-message context opt-in/reset, validation focus, partial cancellation, provider failure, plain-text rendering, account actions and native scoped submission. |
| Repository tooling | 44 tests passed, including disposable-runner lifecycle, explicit fixture mode, Docker fixture refusal and inherited-provider-gate isolation. |
| JavaScript unit checks | 16 passed. |
| Django configuration/schema | System check clean; migration consistency check found no missing migrations. |
| Build and static checks | CSS rebuilt; Portuguese catalogue compiled; Ruff executable checks and diff whitespace checks passed. |

Reproducible browser commands:

```bash
npm run test:e2e -- tests/e2e/assistant/local-chat.spec.js tests/e2e/assistant/connections.spec.js
npm run test:e2e -- --assistant-fixtures tests/e2e/assistant/streaming.spec.js
```

The complete application browser suite was not rerun for this scoped lot.
Current browser evidence covers the assistant's changed surfaces and their
interaction with financial forms; it does not establish every financial route.
Synthetic prompt/context tests verify code boundaries and instruction presence,
not a live model's financial accuracy or resistance to all prompt injection.

## Native installation and live boundary

A verified private SQLite backup preceded the additive `assistant.0003` migration.
The 30 financial/domain tables, including imports and scenario drafts, matched
the backup by row count and content fingerprint after migration and synthetic
chat validation. The installation environment file was not edited. The local
server enabled both gates only in its process environment.

Owner-approved catalogue access loaded the account's eligible model choices.
Its rich metadata exceeded the original 512 KiB response cap; the catalogue now
has a separate 2 MiB bound, covered by large-valid/oversized rejection tests.
SSE events retain their independent 512 KiB bound.

Live inference validation used only the authorized short synthetic question,
without financial context. Initial attempts revealed HTTP 200 SSE data with a
missing Content-Type header. The compatibility path accepts that specific case
only after a bounded first-line check, replays the line into the unchanged SSE
parser and still requires explicit completion. Other MIME mismatches, JSON/HTML,
incomplete streams and transport errors remain failures.

An owner-authorized synthetic request completed using an available model through
the existing ChatGPT-plan connection, returning exactly `Conexão Tuxedo OK.`.
The saved local conversation was reopened and its completed answer verified.
No financial context, API key, paid-API fallback or account switch was used.
Earlier failed diagnostic attempts remain explicit failed local runs.

Final review also corrected two recovery details: native-page refresh now sends
the current asset revision, and cancellation finishes its database reads before
signalling the blocked stream worker. The latter prevents a SQLite read/write
race while preserving immediate same-worker cancellation. Focused regressions
exercise both behaviors.

Raw traces, screenshots, logs and private backup locations stay in ignored local
outputs, outside versioned documentation. No account identifiers, credentials,
financial rows or raw provider error messages are included in this review.

## Remaining limits

Model choices and usage allowance depend on the selected ChatGPT account.
No automatic paid-API fallback exists. Docker's environment wiring is present;
live Docker inference was not exercised. Cancellation closes a transport
immediately within the same worker; other workers observe the persisted state
between chunks, within bounded read/total timeouts. A stopped request may already
have consumed plan usage. Broader financial query tools and action execution
remain outside this delivery.
