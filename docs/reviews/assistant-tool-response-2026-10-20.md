# Assistant tool-response compatibility — 2026-10-20

## Observed failure and evidence limits

The owner reported a failed reply after clarifying a monthly-simulation input.
A read-only inspection of the latest local generation metadata found
`invalid_response` failures without completed-tool evidence. No credentials,
private transcript or provider payload are reproduced here. The existing logs
do not retain the response shape, so they cannot identify its exact rejected
field retrospectively.

Code inspection and an offline reproduction found a concrete incompatibility:
the adapter required `namespace: "tuxedo"` on every returned function call, while
the official [Responses reference](https://developers.openai.com/api/reference/resources/responses/methods/create)
declares `namespace` optional. An otherwise valid advertised function without
that field failed before its callback. This establishes a parser defect, not
proof that this exact field caused the owner's live failure.

## Correction

The adapter now accepts an omitted namespace for an exact advertised function
name. All advertised functions belong to one namespace and have unique names.
Explicit foreign/null/empty namespaces, qualified or unknown names, duplicate
call IDs, incomplete calls and invalid JSON remain rejected. The complete batch
is validated before any callback runs; returned items remain unchanged in
stateless continuation, with `store: false` and the existing bounded loop.

Protocol failures now include a fixed validation-stage label in the existing
redacted diagnostics. Returned tool names, identifiers, arguments, messages and
credentials never enter that label or its log arguments. The current behavior
is owned by [confirmed assistant actions](../assistant/actions.md).

## Validation

The initial offline pass used synthetic SSE, mocked credentials, disposable
databases and the isolated browser runner. No external model, catalogue,
authorization or bank request was made during that pass.

| Check | Observed result |
|---|---|
| Assistant regression suite | 352 cases exercised. Initial run: 351 passed; the new integrated test had an overly strict SQL-write assertion. Final chat-file rerun: all 27 passed, including that integration; the other 325 cases passed unchanged in the initial run. |
| Provider protocol coverage | All 16 provider-tool cases passed, including five new namespace/batch/privacy regressions. Missing namespace preserves stateless history; explicit foreign/null/empty namespaces and unknown names fail before callbacks. |
| Integrated simulation | The real adapter, tool dispatcher and canonical monthly calculator completed using synthetic SSE and an omitted namespace. Owned forecast, payroll deduction and remainder matched the canonical fixtures; financial records, drafts and preferences remained identical. |
| Browser | All 7 streaming cases passed through `npm run test:e2e -- --assistant-fixtures tests/e2e/assistant/streaming.spec.js --workers=1`. Desktop and phone in both themes, real keyboard interactions, financial-draft preservation, failure/cancellation and native fallback are covered. |
| Repository checks | Isolated Django checks and migration-drift check passed, with no new migration. Ruff F, `git diff --check` and the documentation checker passed: 85 documents, 729 local references, zero unresolved. |

The initial test assertion incorrectly rejected the ordinary empty-proposal
metadata update during chat completion. Its corrected allowlist still permits
only chat metadata writes, checks that no proposal was created and compares all
financial/draft/preference rows before and after execution. No production change
was needed for that assertion.

Rendered desktop and phone screenshots were inspected in light and dark themes;
the overlay, composer, focus and financial draft stayed intact. This correction
does not change frontend markup or styles. Raw local evidence is under ignored
`.local/reviews/assistant-protocol-2026-10-20/`: `django.log`, `chat-final.log` and
`browser/`. Browser fixtures never contact the real provider.

## Preservation and remaining check

The existing working tree and running installation were preserved. The
installation database was opened read-only for diagnosis; no migration or
financial-data edit was performed. During the offline pass, no message was
replayed, subscription inference consumed, paid API used, commit created or
publication performed.

At that point, the correction had not been confirmed against another live
provider response. A later owner-initiated test could verify the original
conversation and distinguish failures by the new safe stage diagnostic. Offline
success does not establish live model tool choice or financial-answer quality.

## Follow-up: completion handling

The owner's next live attempt still failed. The supplied safe diagnostic now
located the rejection at `stage=response_output`, before tool dispatch. The
namespace correction alone therefore did not resolve the reported behavior.
This narrowed the failure to the final output boundary without exposing the
private payload.

An additional offline reproducer showed that the parser discarded completed
`response.output_item.done` items and depended exclusively on their repetition
in `response.completed.response.output`. The official
[streaming reference](https://developers.openai.com/api/reference/resources/responses/streaming-events)
identifies done-items as complete and suitable for subsequent reasoning input.
The adapter now retains them by index and releases them only after explicit
response completion and stream closure. Empty/omitted final snapshots can use
that complete collection. Partial batches, conflicting snapshots, invalid or
duplicate indexes, malformed arguments and failed/interrupted responses remain
rejected before callbacks.

The final isolated assistant run passed **all 363 tests**. This includes 27
provider-tool cases, eleven new stream-completion regressions and the integrated
canonical monthly simulation changed to a done-item plus empty final snapshot.
Django checks and migration-drift checks passed. No frontend code or financial
formula changed in this follow-up. Earlier browser evidence above retains its
original scope; the browser suite was not repeated for this parser-only change.
The focused-run evidence is `stream-items-django.log` in the same ignored review
directory. Live connection validation was still pending at this checkpoint and
is not established by these synthetic results.

## Owner-authorized live protocol validation

The owner subsequently authorized up to four short synthetic subscription
requests, without financial data or paid API usage. A dedicated local probe
used the existing selected account/model and the production adapter. It exposed
only a synthetic marker function; no application consultation, financial record
or conversation history was included. The probe did not create chat messages
or financial records.

The first execution passed using **two requests**: one to obtain a function
call, then a stateless continuation with its synthetic result. The observed
wire shape was a completed function in `response.output_item.done` followed by
`response.completed` with `output: []`. The callback ran exactly once. The next
response supplied a completed message item and another empty final output
snapshot; its streamed text matched the expected synthetic marker exactly.
Only fixed schema classifications and the pass/fail result were retained, not
credentials, account identifiers, raw arguments or provider text.

This confirms the compact final response format on the actual connection and
validates the corrected production tool loop. No further production changes
were required after the 363-test run. The other two authorized requests were
not used. The local probe budget was closed after success; no automatic retry,
account/model switch, paid fallback or publication occurred. Local evidence is
`live-tool-attempt-1.log` in the ignored review directory.

This is a protocol check, not a live financial-answer evaluation. The real
financial prompt was not replayed. Canonical payroll/forecast calculations,
owned-data isolation and no-financial-write behavior retain their separate
synthetic integration evidence above.
