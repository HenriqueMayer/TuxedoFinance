# Confirmed assistant actions

Tuxedo can prepare a financial change and show an immutable summary in the chat.
Only the user's separate **Confirm action** POST can save it. A model tool,
message saying yes, or a link cannot confirm. The [assistant guide](../apps/assistant.md)
owns chat, context, provider gates and recovery; the [data model](../data-model.md)
and owning app guides retain financial authority.

## Supported scope

| Action | Confirmation behavior |
|---|---|
| `transaction.create` | Create income/expense through `TransactionForm` and canonical ledger synchronization. Account, PIX, debit/credit cards, native currency, permitted installments, recurrence and cycle rules remain validated. |
| `transaction.categorize` | Change only the reviewed category and update timestamp. Preserve all other source fields, including exact legacy text; category splits and managed redemption/IOF sources keep their existing editor locks. |
| `transaction.update` | Review only explicitly requested changes, including before/after values. Omitted fields preserve saved source data exactly; recurrence/installment scope and generated/split locks remain explicit. |
| `transaction.delete` | Review deletion of the source and its scheduled occurrences; confirm through canonical deletion/ledger handling. No bank movement is initiated. |
| `goal.create` | Create a target through `GoalCreationForm` and `create_goal`, without reserving balances or transferring money. |
| `budget.create` | Create a category/month/currency limit through `CategoryBudgetForm` and `save_budget`, preserving overlap rules. |

No payment, transfer, import, bank connection, alert activation or
unattended financial write is exposed. Unsupported operations retain their
existing application flows. The old `assistant.actions.preview_action` remains
a shape-only helper, separate from these server-validated proposals.

## Preparation and minimal data

`assistant.tooling.financial_tools()` supplies nine provider-neutral function
schemas: bounded `find_choices`, six preparation functions, `read_financial_data` and `simulate_month`. Choices contain
at most 20 owned labels/identifiers with needed native currency/type metadata;
transaction lookup requires a nonempty title query. Choice lookups do not return
balances, notes or the full ledger. Preparation resolves every referenced record from the
current authenticated owner and reuses ordinary forms. It never synchronizes
the ledger or saves a financial record.

These targeted lookups answer the user's question or requested action.
[Owned financial reads and simulations](consultation.md) are available by default;
the visible page is orientation, not an access boundary. The compatible initial
snapshot parameter does not gate tool access. At most five recent action statuses from the same owned chat
can accompany a later question, within its existing context budget. Local choices
and descriptions remain untrusted data.

The complete review summary stays in the local interface. Preparation returns
only the proposal identity, action and pending state to the model, never the
existing source's notes, payment details or full review.

The OpenAI adapter follows the official [function-calling](https://developers.openai.com/api/docs/guides/function-calling)
and [ChatGPT-plan limitations](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations):
namespace `tuxedo`, `store: false`, `stream: true`, stateless continuation with
the returned reasoning/call items and function outputs. Only complete calls after
explicit response completion may invoke the callback; streams close before the
callback. The callback rechecks user/session/run authorization. There are at most
five response requests, ten tool invocations and a shared 90-second budget;
arguments/results are bounded at 16 KiB. Failed/incomplete streams, duplicate
call IDs, unknown tools, unsupported namespaces and malformed JSON fail closed.
The Responses contract makes a returned function call's `namespace` optional.
The adapter accepts an omitted namespace only with an exact advertised function
name: all supplied functions belong to the single `tuxedo` namespace and have
unique names. An explicit namespace must still equal `tuxedo`; null, empty,
foreign or qualified function names are rejected. Returned items are preserved
unchanged in stateless continuation. Protocol-failure logs include only a fixed
validation-stage label, never the returned name, identifier, arguments or text.

The adapter retains complete [`response.output_item.done` items](https://developers.openai.com/api/reference/resources/responses/streaming-events)
by output index, including the completed opaque reasoning needed for stateless
continuation. It waits for `response.completed` and closes the stream before
dispatch. If the final response omits its output snapshot or supplies an empty
list, the completed items supply that output. Every observed slot must be
complete and indexes must be contiguous, unique and bounded to 32 items; a
nonempty final snapshot must agree with the completed items. Added items,
argument deltas and argument-done events alone never authorize a callback.
Malformed snapshots, incomplete batches, EOF, cancellation and failed responses
never execute a collected call. The existing aggregate history budget also
bounds retained done-items.

This is not automatic retry, provider/model substitution or a paid API fallback.

## Review, confirmation and recovery

Additive migration `0006_actionproposal` creates private review metadata, not
financial rows. Proposals belong to a conversation and session, expire after
30 minutes, and retain normalized parameters, reviewed summary and dependency
digest. Equivalent normalized proposals in one generation share one request
identity. They are attached to the assistant reply only after its run completes.
Failed, stopped or running generations cannot expose executable review controls.

The server accepts only the opaque proposal UUID, CSRF and validated local scope
at `/assistant/actions/<uuid>/confirm/` or `.../cancel/`. Client financial parameters
are rejected. Confirmation checks owner/session, completed run, expiry and current
referenced state, then reruns forms and canonical services. A changed dependency
requires a fresh proposal. An atomic row claim prevents concurrent duplicate
writes; repeat confirmation returns the saved result. Storage/validation failures
roll back the operation and never become a success message.

Discard changes review metadata only. It does not delete any financial record.
Native forms work without JavaScript; the overlay also preserves chat drafts,
focus, transcript position and unrelated edited financial forms. Summary text is
escaped, result links are local and remain subject to normal destination ownership.
Generations and confirmations are separate: stopping a reply cannot undo a
previously confirmed record.

Deleting a conversation cascades its proposals, not the financial records they
created. Proposal metadata follows the local database's private-history and
backup lifecycle. No financial authorization follows from a recorded result URL.
Validation evidence and actual live-provider limits belong in dated reviews.
