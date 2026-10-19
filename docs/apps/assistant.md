# `assistant`

**Current status:** Local assistant foundation under Unreleased after `0.10.0`.
No provider is connected. The application does not generate model answers,
consume a ChatGPT plan, initiate bank payments or execute financial actions.
The developer version is unchanged; this is preparation for later evolution,
not a released integration.

The app owns private conversation storage, a provider-unavailable state,
structured financial context and explicit future provider/action contracts.
The existing Django account remains the authorization boundary. The
[Open Finance study](../reviews/open-finance-personal-study-2026-10-18.md)
is separate research, not a data source for this assistant.

## Routes and local storage

Follow the normal [upgrade steps](../operations.md#updating-a-native-installation)
before opening chat in an existing installation. The new migration only adds
assistant tables. Use disposable data for validation as described in Contributing.

| Route | Behavior |
|---|---|
| `/assistant/` | Authenticated conversation entry page and native fallback. |
| `/assistant/<uuid>/` | Read an owned conversation; UUIDs do not replace ownership checks. |
| `/assistant/conversations/new/` | CSRF-protected POST creating an empty local conversation. |
| `/assistant/<uuid>/delete/` | CSRF-protected POST deleting only the owned conversation and its messages. |
| `/assistant/<uuid>/messages/` | Returns provider-unavailable HTTP 503; no fake user message, answer or successful inference is saved. |
| `/assistant/context/` | Authenticated GET collecting a bounded, read-only structured snapshot for an authorized originating route. |

The `X-Tuxedo-Assistant: panel` request header selects the assistant HTML
fragment. It is a presentation choice, not authentication or permission to read
another user's conversation/context. Private page, fragment and context
responses retain the application's no-store and reauthorization rules.

`Conversation` has an owner, UUID, optional title up to 120 characters and
created/updated timestamps. `Message` has its own UUID, conversation, user or
assistant role, text and creation timestamp. Conversation history is paginated
at 30 entries; detail reads the latest 200 messages in chronological order.
These are display bounds, not automatic deletion policies.

Conversations and messages are local database data, retained until explicitly
deleted. They are not browser-storage transcripts, shared global history or an
OpenAI conversation store. Normal database backups can retain older copies
after deletion; see [operations](../operations.md#assistant-data-and-integrations).
The unavailable composer is disabled, and a stale/direct message POST fails
explicitly instead of silently accepting unsent work.

## Structured financial context

Context starts from the current Django user and a signed, expiring origin scope.
The scope contains an allowlisted local route and permitted query parameters;
it is bound to the current owner. The server resolves that route and rechecks
ownership of referenced records. It never trusts a raw client-supplied model,
object ID, label, total or arbitrary URL as financial authority.
`assistant.context` owns normalization/signing and applies a one-hour lifetime
(`SCOPE_MAX_AGE = 3600`). Local locations are limited to 2,048 characters and
30 query fields; unsupported filters are refused rather than copied wholesale.

The collector returns the supported scope, snapshot timestamp, financial cutoff,
reporting currency, metrics, evidence warnings and owned source links. The compact
Context block shows only the current workspace/period and its authorized origin
link. It does not repeat financial figures, technical timestamps or the evidence
inventory. The structured endpoint retains canonical ISO dates, numeric strings,
currencies and warnings for future response construction. Incomplete evidence
must remain explicit in any later answer rather than being treated as a zero
balance or a complete ledger review. Page location is a UI cue, not a claim that
every customer record was fetched or a replacement for server-side ownership.
Future agent queries may consult the authenticated user's financial data beyond
the page currently open, retrieving what the question needs rather than copying
the whole database into each request. This disconnected foundation retains the
bounded collector below; broader query tools belong to later provider work.

| Current context surface | Collected evidence |
|---|---|
| Unfiltered Home and Accounts/bank detail | Up to 20 owned account balances at today's financial cutoff, each in its native currency, with source links and unknown-opening warnings. |
| Unfiltered Transactions/list or owned editor/split | Up to 20 stored source amounts linked to owned banking instruments, with date, income/expense and recurring/installment/future-source labels, plus editor links where permitted. Unlinked cash sources are not copied. These are not realized cash flows, account balances, split totals or billed-month installment totals. |
| Reports, invoices and other filtered financial pages | Owned source location and a warning that detailed filtered calculations are not included; no guessed total. |
| Other allowlisted Categories, Investments, Plan, Sandbox, completed import history/detail and Settings pages | Owned source location and an explicit warning that detailed figures are not automatically copied. No import file, scenario input or settings payload is scraped. |

The allowlist covers selected list/create/edit/detail routes, not every route in
those apps. Only completed confirmed/undone import detail is eligible; paused
operations and pending batches stay unavailable. Every snapshot warns that stored
projections were not refreshed. A 20-source cap is disclosed when truncation
occurs; the reporting currency metadata does not mean native values were
silently converted or summed.

Collection is read-only. It does not call request-time ledger synchronization,
create missing derived rows, invoke mutation services or fetch an external URL.
This differs from ordinary workspace pages that may synchronize before
rendering; see [request-time synchronization](../architecture.md#request-time-synchronization).
Do not scrape the DOM, hidden inputs, unsent forms, arbitrary import files or
the user's entire browser/conversation history to construct context. Names,
notes, descriptions and other record text are untrusted data, not instructions
authorizing tools or writes.

The snapshot is evidence from a particular time and scope, not a live guarantee.
Opening another page or changing filters requires a fresh authorized scope;
switching users invalidates the previous user's scope. Source links remain
subject to their destination's normal ownership, generated-record edit locks
and paused-feature gates.

## Interface and recovery

The authenticated shell offers the assistant as a utility, preserving the same
five primary destinations. Its fixed desktop overlay lives outside `main` and
never reserves width or changes page/filter/form geometry. Narrow screens retain
the accessible modal sheet. Chat actions never submit or capture a financial draft.
Following Context to the current document closes the panel without reloading
that document; navigation-only origins and empty filters do not change this rule.
The cat/orbit artwork has gentle transform-only motion inside stationary controls,
disabled by reduced-motion preference. A whole-body HTMX navigation reconstructs
the panel and refetches the selected conversation with authenticated owner
checks; it does not preserve or replay a DOM transcript. The full-page route
remains available without JavaScript. Shared colors, typography, actions,
focus, viewport clearance and mobile navigation rules apply; the owning
[navigation contract](../frontend/navigation.md#assistant-panel) defines panel
interaction and page continuity.

Provider unavailable, empty conversation, loading failure, unauthorized/stale
context and deleted conversation are explicit states. They must not display a
simulated model reply or imply an external connection. Conversation creation
and deletion are explicit local POSTs, not financial mutations. Native requests
retain CSRF, ownership and server-rendered recovery.
Closing/reopening clears hidden transcript/context HTML while an authorized
reload is pending. Only the selected owned conversation identifier survives in
page memory; it is not permission to replay its content after a session change.

## Provider and action boundary

The provider boundary defines future response streaming, cancellation and error
handling. It is not a running model, background worker, credential store or
automatic fallback. The current unavailable state remains authoritative until a
separately approved provider implementation exists.

| Python interface | Current contract |
|---|---|
| `assistant.providers.get_provider()` | Returns `DisconnectedProvider`; no credential lookup, transport or live generation. |
| `providers.base.GenerationRequest` | Explicit JSON context object, at most 32,000 characters, plus at most 20 selected `ChatTurn` entries, `language` (`en` or `pt-br`) and the supported instruction version. This constructor checks shape/bounds, not ownership. |
| `ChatTurn` | User/assistant role and at most 4,000 text characters. The request does not automatically include all locally stored history. |
| `ProviderEvent` | Typed `text`, `error` or `done` event; per-event text/code bounds. `ProviderUnavailable`, `ProviderCancelled` and `ProviderError` expose stable error codes rather than adapter exception text. |
| `CancellationToken` and `stream_response` | Cooperative cancellation between events, typed terminal/error handling and iterator closure; no output persistence or HTTP streaming endpoint. Generation is refused inside a database transaction. |
| `assistant.actions.preview_action` | Shape-only allowlisted proposal, returned as an immutable `ActionPreview`; no object lookup, simulation of financial results or execution. |

A later transport adapter must supply bounded network timeouts and close its
transport when iteration closes. Cooperative cancellation cannot interrupt an
adapter blocked in I/O. Authorization and deliberate persistence remain the
caller's responsibility; constructing a valid request does not make arbitrary
JSON authorized context.

Current dry-run previews set `requires_review=True`, `executable=False` and warn
that ownership, compatibility and current state have not been validated. A
preview is not proof of a valid account/category, a financially valid plan or a
saved transaction. These Python proposal shapes are not executable UI commands:

| Proposal name | Shape-only meaning |
|---|---|
| `transaction.create` | Bounded title, native amount/currency/date, income/expense type and account/category identifiers. No transaction or settlement is created. |
| `transaction.categorize` | Transaction/category identifiers; no category or split is changed. |
| `goal.create` | Name, target amount/currency and optional target date; no goal or cash reservation is saved. |
| `budget.create` | Category, `YYYY-MM`, currency and amount; no limit or copied budget is saved. |
| `alert.propose` | Allowlisted suggested kind, summary and local source URL; no signal, notification, watcher or automatic decision is created. |

No execution endpoint is exposed. Future mutations must use canonical financial services,
revalidate ownership/current state and apply the explicitly authorized bounded
rule or review decision; model text cannot expand that authorization. Stopping
a stream would not by itself undo an already confirmed action, so any future
implementation must keep generation and confirmation separate.

## Versioned instructions and evaluation limits

`assistant.prompts.INSTRUCTIONS_VERSION` is `v1`; `load_instructions` loads the
matching `assistant/prompts/v1/system.txt` and refuses unknown versions. The
instructions require supplied owned source links, explicit missing/stale/bounded
evidence and separation of native currency, source amounts, installments,
settlement, cost and projections. The selected English/Brazilian Portuguese
language, concise practical style, facts versus estimates/suggestions and focused
questions for missing information are explicit written obligations. Record text and chat history are untrusted
data rather than authority to change instructions, access credentials or execute
tools. The unavailable-provider status must remain honest.

These are versioned local instructions and interface guards. Offline tests can
check deterministic boundaries and fixtures; they do not establish the quality,
financial correctness or injection resistance of a live model. No provider or
real-model evaluation is part of this implementation. Any later model-backed
evaluation needs its own approved account/context/usage scope and evidence.

## Planned OpenAI connection

**Planned, not implemented. Official documentation checked 2026-10-18.**
The intended next provider is an explicit Sign in with ChatGPT connection linked
to an already authenticated Django user. It does not replace local login, grant
another user's financial access or enable a paid API-key fallback.

[OpenAI's quickstart](https://developers.openai.com/siwc/quickstart) distinguishes
identity scopes from optional ChatGPT-plan inference permission and distinguishes
partner website sign-in from the local/open-source plan-usage route.
[The plan-usage overview](https://developers.openai.com/siwc/token-sharing-open-source)
documents eligible local applications and user/workspace-bound registrations;
paid/remotely hosted deployment has a separate access process. This repository's
PolyForm Noncommercial license is not proof of eligibility under an open-source
program. Confirm the actual local/deployment route and terms before building it.

[ChatGPT's user guide](https://learn.chatgpt.com/docs/sign-in-with-chatgpt)
describes eligible Plus/Pro users authorizing plan usage, shared existing limits
and access/usage management. This permission does not expose the user's ChatGPT
conversations or memories and does not create an extra allowance. Availability,
model access and limits must be checked for the actual account; the application
must explain unavailable or exhausted usage without changing billing routes.

The current [preview contract](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations)
requires streamed HTTP Responses requests with `store: false`; HTTP continuation
does not provide persistent server conversation storage. A later adapter must
check that contract again, manage OAuth credentials securely per linked user and
send only deliberately selected local context/history. No such authorization,
credential, network request or live inference is part of this foundation.

## Later automation

Opt-in assistance while the application is in use remains planned. There is no
daemon, schedule, unattended model invocation, bank refresh or background
financial write. Before adding automation, define its trigger, bounded context,
usage limits, visible progress/cancellation and review boundary. It cannot reopen
the paused ingestion workflow. A previously enabled, explicitly bounded rule may
authorize later transaction creation/categorization; otherwise a proposal needs
the applicable explicit review. No such rule or execution runs in this foundation.

For source-checkout validation, use the isolated checks in
[Contributing](../../CONTRIBUTING.md). Current results and visual evidence belong
in the implementation's dated review, not in this feature contract.
