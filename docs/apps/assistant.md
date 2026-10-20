# `assistant`

**Current status:** Local conversations, OpenAI authorization and gated model
catalogue/streaming implementation under Unreleased after `0.10.0`.
Authorization and inference are independently disabled by default.
Owner-approved native sign-in and local account confirmation were
observed; see the [bounded native validation](../reviews/assistant-native-sign-in-2026-10-19.md).
That observation did not establish live model availability or streaming. With
either gate off, the provider/composer remains unavailable and makes no model
catalogue or inference request. When both are explicitly enabled, an eligible
selected account can load its models and submit a chosen-model request. No
bank payment or paid API-key fallback is implemented. Local financial proposals
have a separate explicit user confirmation path described below.

A later [bounded streaming validation](../reviews/assistant-streaming-2026-10-19.md)
completed a short owner-authorized synthetic request through the ChatGPT-plan
connection. It does not establish financial-answer quality, every model's
availability or live Docker inference.

The app owns private conversation storage, user-owned connection metadata, an
encrypted local credential vault, a provider-unavailable state, structured
financial context, targeted read/calculation tools and confirmed local actions.
The existing Django account remains the authorization boundary. The
[Open Finance study](../reviews/open-finance-personal-study-2026-10-18.md)
is separate research, not a data source for this assistant.

## Routes and local storage

Follow the normal [upgrade steps](../operations.md#updating-a-native-installation)
before opening chat in an existing installation. The additive assistant
migrations create conversation, authorization and generation-run tables. The
additive reasoning-effort migration leaves existing runs at Model default. They
do not alter financial records. Use disposable data for validation as described
in Contributing.

| Route | Behavior |
|---|---|
| `/assistant/` | Authenticated conversation entry page and native fallback. |
| `/assistant/<uuid>/` | Read an owned conversation; UUIDs do not replace ownership checks. |
| `/assistant/conversations/new/` | CSRF-protected POST creating an empty local conversation. |
| `/assistant/<uuid>/delete/` | CSRF-protected POST deleting only the owned conversation and its messages. |
| `/assistant/<uuid>/export/`, `.../messages/<message-uuid>/export/` | Authenticated owner GET/HEAD exporting raw Markdown for the complete conversation or one message; private download and enhanced clipboard paths never call a provider. |
| `/assistant/messages/`, `/assistant/<uuid>/messages/` | CSRF-protected POST for a new/existing owned conversation; validates selected account/model/context, streams SSE to an enhanced client or waits and redirects natively. Gate-off requests return unavailable without a fake exchange. |
| `/assistant/models/` | Authenticated owned-account catalogue/state GET; no external call with either gate off. |
| `/assistant/actions/<uuid>/confirm/`, `.../cancel/` | Owned-session CSRF POST confirming or discarding an immutable local proposal; model text cannot confirm. |
| `/assistant/preferences/` | CSRF-protected POST remembering only the selected owned account's validated model and reasoning effort. No message or financial context is accepted. |
| `/assistant/runs/<uuid>/cancel/` | CSRF-protected owner/session POST cancelling a generation run; no financial rollback. |
| `/assistant/context/` | Authenticated read-only context GET: minimal page metadata by default; bounded financial evidence only with explicit `include_context=1`. It never calls a model. |
| `/assistant/connections/` | Authenticated, owner-scoped settings GET: local account metadata and pending authorization status; no vault initialization or external request. |
| `/assistant/connections/start/`, `/assistant/connections/<uuid>/authorize/` | Explicit CSRF-protected native POST starting a new link or reauthorization; refused while real authorization is disabled. |
| `/assistant/connections/callback/` | One-time loopback OAuth GET; validates the handoff without requiring a callback-host cookie and redirects to the neutral result page. It does not attach an account to a Django user. |
| `/assistant/connections/callback/result/` | Generic callback result GET, without authorization codes, state, tokens or account details. |
| `/assistant/connections/attempts/<uuid>/finish/`, `.../cancel/` | CSRF-protected POST confirming or cancelling an owned attempt from its original authenticated Django session. |
| `/assistant/connections/<uuid>/activate/`, `.../disconnect/` | CSRF-protected owner POST selecting local account metadata or clearing reusable credentials; conversations and financial records remain. |

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
An unavailable composer is disabled and direct submissions fail explicitly.
Eligible submissions persist the user message and a session-bound `GenerationRun`,
including its selected model and optional reasoning effort;
its completed/failed/cancelled state and any bounded partial assistant text stay
in local history. Request UUID retries replay the existing terminal result,
without submitting another provider request. Conflicting reuse, including a
different effort for the same request UUID, is refused. A failed
or cancelled exchange is not silently reused as completed model history.

## Structured financial context

Context starts from the current Django user and a signed, expiring origin scope.
The scope contains an allowlisted local route and permitted query parameters;
it is bound to the current owner. The server resolves that route and rechecks
ownership of referenced records. It never trusts a raw client-supplied model,
object ID, label, total or arbitrary URL as financial authority.
`assistant.context` owns normalization/signing and applies a one-hour lifetime
(`SCOPE_MAX_AGE = 3600`). Local locations are limited to 2,048 characters and
30 query fields; unsupported filters are refused rather than copied wholesale.

`assistant.context_request.build_context` returns timestamp, financial cutoff,
language and optional current-page label/route/date-period filters by default.
It does not eagerly collect financial metrics or preferences. Free-text search
and record-filter IDs are omitted from transmitted page metadata. The compatible
`include_context` parameter can request a bounded initial-page snapshot; without
a signed origin it supplies no financial figures. It is separate from the
default [owned consultation tools](../assistant/consultation.md), which retrieve
only evidence needed for the question from any supported owned workspace.
The current composer has no page-data checkbox and the page is not an access
boundary. The optional snapshot supplies reporting/native currencies, metrics,
evidence warnings and verified owned references. Labels become bounded plain
text; notes, raw HTML, unsent fields and other model fields are excluded. The compact
Context block shows only the current workspace/period and its authorized origin
link. It does not repeat financial figures, technical timestamps or the evidence
inventory. Financial context retains canonical ISO dates, numeric strings,
currencies and warnings. Default JSON is capped at 32,000 characters, including
Unicode escapes, with deterministic trailing-row/reference truncation and an
explicit warning. A retained zero remains zero; missing amounts or FX remain
unknown. Incomplete evidence
must remain explicit in any later answer rather than being treated as a zero
balance or a complete ledger review. Page location is a UI cue, not a claim that
every customer record was fetched or a replacement for server-side ownership.
Targeted tools can consult saved records beyond the page currently open without
copying the whole database into each request. Their separate evidence and
calculation contract lives in the [consultation guide](../assistant/consultation.md).
The retained optional initial-page collector has these narrower surfaces:

| Optional initial-page snapshot surface | Collected evidence |
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
six primary destinations. Its fixed desktop overlay lives outside `main` and
never reserves width or changes page/filter/form geometry. Narrow screens retain
the accessible modal sheet. Chat controls never submit or capture an unrelated financial draft.
The compact conversation layout keeps local history, the current-page link and
a persistent composer available while the transcript scrolls. Short software-
keyboard viewports use compact chrome and a 44px editor cap; the native full
page remains vertically scrollable. A compact titlebar groups the unchanged mark
and title with stationary 44px Minimize and Close controls, paired without heavy
individual outlines. Local history remains accessible without a redundant
visible subtitle. Minimize keeps the
current draft, model/effort choices and active reply behind a restore tab in the
current document. The restore tab also exposes Close without reopening the panel.
Restore reauthorizes the user/session before revealing content;
an expired or different session discards hidden temporary state. Close cancels
the reply and clears the unsent message and temporary request state without
deleting saved history or deliberately saved model/effort preferences.
If the linked account changes while minimized, retain same-session unsent text
but use the new account's freshly authorized settings.
History, the compact current-page badge and New/Delete actions share one toolbar
above the transcript. Context and message-role labels remain accessible without
repeated visible headings. Center the empty-state artwork and copy. Compact chat
type, restrained message spacing and a shallow composer keep the conversation
prominent. The composer frame owns its border and theme-aware focus ring. A
deliberate Chat settings gear holds the labelled native Model and Reasoning
effort selects; a single-line caption identifies the selection without occupying
the message area. Long captions retain their full accessible text. The enhanced
keyboard hint appears while the composer is focused, without moving its layout.
The page badge remains orientation; the composer has no financial-access
checkbox. The gear and Send/Stop remain available. Their visual faces may be smaller, but
interactive targets, including the editor and page link, remain at least 44px.
Native model/effort controls retain their validated submission
contracts. Settings use a native disclosure without a focus trap: Escape closes
it before minimizing chat, and outside click or Tab-away dismisses it. The bounded
settings surface opens above the composer and scrolls internally on short screens.
Invalid submitted settings reopen for recovery, including without JavaScript.
Following Context to the current document minimizes the panel without reloading
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
While an enhanced send waits for the first text, show a compact Thinking state
inside the transcript, including time spent waiting for response headers. Change
to Writing a response only when text actually arrives. These states describe
request progress; they do not claim that financial records have been consulted
or calculations performed. The workspace remains usable and Stop remains
reachable. Completion, cancellation, invalid input and failures remove the waiting
indicator; reduced-motion preferences disable its decorative animation.

Assistant replies use a local, dependency-free Markdown presentation subset on
initial display and during streaming: paragraphs, emphasis, headings, simple
lists, quotes, code, rules and pipe tables. Raw HTML is literal text. Model-made
links and images remain inert labelled text; only the separately validated local
references are actionable. Rendering creates allowlisted DOM elements and text
nodes without assigning provider text to HTML. The existing 16,000-character
reply bound applies before parsing; nested formatting and table columns are
bounded. This is not a full CommonMark parser. User messages retain their plain
text, and native requests without JavaScript retain escaped, readable Markdown
source rather than execute a second renderer.
The enhanced view keeps one server-verified reference footer. It omits a final
paragraph consisting only of Markdown links when every destination and source
label match that message's authorized footer. An ISO month suffix is equivalent
only when it matches the single month in that authorized URL. This applies after stream completion
and when reopening saved history. Inline explanations, code, quoted text,
images, explanatory link labels and unverified or differently filtered links stay visible and inert.
The original message and Markdown exports are unchanged; generated text never
creates an active link or expands the server's reference scope.
Closing or replacing the panel clears hidden transcript/context HTML before an
authorized reload. Minimize retains it only in the hidden current-document panel;
the restore GET must validate the same user and session before revealing it or
reapplying temporary choices. The selected owned conversation identifier is not
permission to replay its content after a session change.

## Markdown copying

Conversation options include Copy conversation as Markdown; each message has
Copy as Markdown below its content. Authenticated export routes preserve raw
Markdown, complete history beyond the 200-message UI limit and verified local
references/action-review state. Native links download `.md` without JavaScript.
Enhanced copies fetch fresh owned content and reauthorize the same user/session
after the body finishes, before writing to the clipboard. Live partial text also
requires fresh authorization. A failed clipboard operation exposes a deliberate
download fallback. Exports never resolve a provider or collect financial context.

## Saved chat settings

The last explicitly selected model and reasoning effort live in the local
`ProviderConnection.last_model_slug` and `last_reasoning_effort` fields, scoped
to its Django user and linked account. Migration `0005` adds these blank fields;
it does not infer a preference from earlier conversations or edit financial
records. First use remains empty. An authorized composer GET revalidates the
saved pair against the current account's catalogue. An unavailable model renders
empty; an unsupported effort renders Model default for the still-available model.
GET does not rewrite preferences or choose a different model/account.

Enhanced native selects save deliberate changes through `/assistant/preferences/`.
Requests contain only CSRF, connection ID, model and effort; the server rejects
extra fields, stale/foreign accounts and invalid pairs. Changes are serialized
and the next chat load waits for pending saves, so delayed responses cannot
replace a newer choice. Failed saves expose a retry inside Chat settings.
The Saved confirmation marks durability; reloading the browser while Saving is
still shown can discard a change waiting behind an unfinished request.
Accepted Send also saves the validated pair, including without JavaScript.
Native redirects and enhanced completion GETs do not put model/effort into the
URL, allowing subsequent loads to use the latest preference. Explicit legacy
GET values and bound POST errors retain precedence for recovery.

Closing, creating a conversation and reloading keep saved settings, while
temporary drafts retain their separate lifecycle.
The browser stores no preference in local/session storage. Saving preferences
does not update the connection's credential-lifecycle timestamp, enable a
provider, generate a message or change its billing route. Model default persists
as blank effort; a deliberate blank model/effort clears the remembered choice.
The Design Lab keeps only synthetic page-memory settings, discarded on reload.

## Provider and action boundary

`ASSISTANT_OPENAI_INFERENCE_ENABLED` defaults to `False`, separately from
`ASSISTANT_OPENAI_AUTH_ENABLED`. Both must be enabled and the current user must
have a selected `ready` connection with direct-plan/invoke scopes. Otherwise
provider resolution, composer rendering, model-list GETs and message POSTs cannot
open an external model connection. Enabling authorization alone is insufficient.
When inference is enabled, opening a ready composer may fetch the account's model
catalogue and refresh expiring credentials; this is an external request even
before Send. The connection-settings GET itself remains local/read-only.

The public `https://api.openai.com/v1/models` and `/v1/responses` endpoints are
used only with the selected account's authorized ChatGPT-plan OAuth token.
The adapter never reads `OPENAI_API_KEY` and exposes no API organization/project,
API-key configuration or separate API billing route. It never falls back to a
paid API key when plan access, quota or a request fails.

The adapter follows the official [models and inference guide](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference):
it reads the selected account's `/v1/models` catalogue, keeps `visibility: list`,
shows `display_name` and submits the explicitly selected `slug`. No model is
invented or substituted automatically; only a previously explicit, currently
valid saved choice is restored. A short owner/connection-specific
cache avoids repeated catalogue requests; account changes invalidate that scope.
Send revalidates the selected connection and catalogue choice. An empty catalogue,
reauthorization requirement or request error remains a visible recovery state.

Reasoning effort is optional and model-specific. Only supported values advertised
by the selected account's catalogue are offered; names alone never establish
support. **Model default** sends no `reasoning.effort` override. An explicit
selection is validated against the selected model again on Send, and an
unsupported model/effort combination is a recoverable field error. Changing the
model in the enhanced composer keeps a compatible effort; an incompatible one
returns to Model default with an announcement. This never substitutes another
model or enables separate API billing. The native form retains labelled choices
and server-side compatibility validation without JavaScript.

| Python interface | Current contract |
|---|---|
| `assistant.providers.get_provider(user, connection_id)` | Resolves the explicitly gated owned selected account to `OpenAIProvider`; returns `DisconnectedProvider` when unavailable. Tokens stay in the server process/vault. |
| `providers.base.GenerationRequest` | Explicit model/effort, JSON context up to 32,000 characters, bounded history, language and instruction version; optional bounded function schemas and a server-owned proposal callback. Constructor validation does not authorize records or writes. |
| `ChatTurn` | User/assistant role with bounded text. Prior history is limited to 4,000 characters per supplied message; full local history is not automatically transmitted. |
| `ProviderEvent` | Typed `text`, `error` or `done` event; per-event text/code bounds. `ProviderUnavailable`, `ProviderCancelled` and `ProviderError` expose stable error codes rather than adapter exception text. |
| `CancellationToken` and `stream_response` | Typed terminal/error handling, registered transport closure and explicit completion; EOF/incomplete/interrupted streams never imply success. Provider I/O is refused inside a database transaction. |
| `assistant.actions.preview_action` | Shape-only allowlisted proposal, returned as an immutable `ActionPreview`; no object lookup, simulation of financial results or execution. |
| `assistant.tooling` / `assistant.action_service` | Bounded owned choice lookup and canonical review preparation; a distinct authenticated confirmation runs ordinary financial validation and services. |

Responses use public `/v1/responses` HTTP SSE with `store: false`, `stream: true`
and no server-conversation/continuation ID. Explicit effort uses
`reasoning: {"effort": "<advertised level>"}`; Model default omits that field.
The current question, minimized context and up to nineteen completed history
turns are the initial outbound content. Nine local functions provide targeted
consultations, canonical monthly CLT simulations, owned choices and six
preparation actions. Reads and simulations need no extra confirmation; proposals
cannot confirm or write financial records. See
[application consultations](../assistant/consultation.md). Hosted connectors, automatic
retry and paid fallback are not supplied. The [preview limitations](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations)
remain the upstream request contract.

The enhanced UI renders streamed deltas through its safe Markdown subset, exposes Cancel and keeps
references as separately verified local links. The native POST waits for the
bounded run and redirects to its owned history, without JavaScript. Runs retain
explicit terminal status, at most 16,000 output characters and a 90-second budget;
transport reads are bounded at 15 seconds. Only explicit nonempty
`response.completed` output completes successfully. Session, user, connection
and run authorization are rechecked before exposing text after blocking reads.
Cancel records terminal state in the database. A process-local weak registry
also closes the active transport immediately when the cancel request reaches
the worker serving that stream. Other workers observe cancellation through
database rechecks between chunks; a blocked read can take its 15-second bound
to unwind, within the 90-second total budget. Response closure and departure
also signal cancellation. Cancellation cannot undo provider work
already performed or guarantee zero usage. Partial output remains visibly
failed/cancelled locally and is excluded from later completed history.

A crashed worker may leave a run marked running. The next eligible deliberate
send marks runs older than the 90-second budget failed/interrupted before
accepting new work. It never automatically resubmits that POST or repeats the
inference request; an identical request UUID retains its existing terminal result.

Stable unavailable, unauthorized, rate/usage-limit, incomplete, interrupted,
timeout and transport errors reveal neither credentials nor raw provider bodies.
Catalogue JSON is bounded at 2 MiB and error JSON at 64 KiB. Diagnostics retain
only fixed mapped status/code/parameter values, MIME classifications and body
kind; they never log raw response content, prompts, tokens or account identity.
For HTTP 200 streams with a missing `Content-Type`, compatibility is limited to
a bounded first-line check identifying valid SSE. The consumed prefix is replayed
unchanged through the ordinary parser. Explicit wrong MIME types and non-SSE
bodies are rejected; event-schema and terminal-completion checks remain intact.
The check creates no synthetic progress or API-key fallback. This rule alone
does not establish that a live request completes successfully.
The official [errors and recovery guide](https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery)
distinguishes app/plan usage limits from exhausted overall allowance; the app
does not invent reset times, quota totals or guaranteed model access. No error
silently switches model, account, billing route or retries the generation.

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

The legacy shape-only helper above remains unchanged. The separate
[confirmed action workflow](../assistant/actions.md) supports those first four actions and transaction update/delete through `ActionProposal`, additive migration `0006` and native POST
confirmation cards. Alert proposals remain non-executable. User/session ownership,
expiry, current financial state and canonical forms/services are checked again
when confirming; a provider response cannot confirm. Stopping a stream cannot
undo an already confirmed action.

## Versioned instructions and evaluation limits

`assistant.prompts.INSTRUCTIONS_VERSION` is `v6`; `load_instructions` defaults to
`assistant/prompts/v6/system.txt`, retains explicit v1/v2/v3/v4/v5 loading for historical
requests and refuses unknown versions. The
instructions require supplied owned source links, explicit missing/stale/bounded
evidence and separation of native currency, source amounts, installments,
settlement, cost and projections. The selected English/Brazilian Portuguese
language, concise practical style, facts versus estimates/suggestions and focused
questions for missing information are explicit written obligations. Record text and chat history are untrusted
data rather than authority to change instructions, access credentials or execute
tools. V2/v3 do not hardcode provider availability; they explicitly distinguish
minimal page metadata from opted-in financial evidence and grant no tool or
financial execution authority.

V3 names the assistant **Tuxedo, your financial assistant**, or **Tuxedo, o seu
assistente financeiro** in Brazilian Portuguese. It adds practical personal-finance
premises: comparable evidence, goal/horizon/liquidity framing, measurable
proposals and explicitly conditional scenarios. It states that the application
has no live web/news verification tools and does not inherit ChatGPT/Codex
plugins. Pasted articles remain unverified data. The
[financial premises and research boundaries](../assistant/financial-premises.md)
own methodology provenance and future-news acceptance requirements; reading
that document does not connect a tool or provider. V4 preserves those premises,
adds concise Markdown and distinguishes tool-prepared proposals from
application-recorded execution. V5 enables owned application reads by default and directs requested monthly scenarios to canonical calculation tools; only ambiguous inputs need clarification. Chat text cannot confirm a proposal.
V6 preserves those rules and aligns source attribution with the automatically
rendered reference footer. It uses source labels in explanatory prose where
useful, without repeating paths, Markdown links or source lists. Missing or
incomplete evidence still requires an explicit explanation.

These are versioned local instructions and interface guards. Offline tests can
check deterministic boundaries and fixtures; they do not establish the quality,
financial correctness or injection resistance of a live model. Model-backed
evaluation needs its own approved account/context/usage scope and dated evidence;
implemented transport and a successful authorization are insufficient.

<a id="planned-openai-connection"></a>

## OpenAI authorization preparation

**Implemented preparation, with real authorization disabled by default. Official
documentation checked 2026-10-19.** Settings exposes the owned account lifecycle
without replacing Django login or enabling the separate inference gate. Synthetic accounts,
signed-token fixtures and injected transports belong only in isolated tests;
the application never seeds or displays a fabricated connected account.

### Authorization gate and local callback

`ASSISTANT_OPENAI_AUTH_ENABLED` defaults to `False`. Its explicit environment
opt-in requires the owner's approval for live account authorization. Opening
connection settings does not enable it, initialize the vault or contact OpenAI.
The saved account's local selection and installation availability are separate
states. A disabled authorization or inference setting leaves the selected link
stored; settings must identify that local selection and explain the disabled
capability instead of implying that selection alone makes chat usable. The
panel names the blocked capability and links to settings. Status inspection must
not initialize/decrypt the vault or contact the provider while either gate is off.
The separately gated composer catalogue behavior is defined above. Setting the
authorization flag alone does not start authorization; the owner must submit the native Continue with ChatGPT
POST, which opens authorization in a new tab while preserving the original
settings tab for final confirmation. The
[native validation](../reviews/assistant-native-sign-in-2026-10-19.md) records the
owner-approved account link and preserved installation boundary. Account linking
does not turn on the separate inference gate or prove a listed model can respond.

`ASSISTANT_OPENAI_CALLBACK_URL` defaults to
`http://127.0.0.1:8000/assistant/connections/callback/`. The prepared protocol
accepts only HTTP, the literal `127.0.0.1`, an optional valid port and that exact
path, without credentials, query or fragment. Do not substitute `localhost`, a
LAN address, HTTPS or another callback path. The browser must run on the same
computer as the native service or Docker host; a phone's loopback address points
to the phone. For Docker, use the published host port, as described in the
[Docker guide](../docker.md#assistant-authorization-preparation).

The callback host can differ from the original `localhost` session host. A
validated callback therefore stages the verified identity without logging the
visitor into Django or immediately attaching the account. The owner returns to
the original settings tab, refreshes it, reviews the identity and submits Confirm
account link. A different Django user or browser session cannot finish that
handoff. The settings form preserves the browser's same-origin CSRF identity;
its narrow form-action policy permits only the official authorization redirect.
Callback pages use no-store and no-referrer responses and promptly
redirect away from the authorization query.

### Protocol and account lifecycle

`assistant.connections.oauth` prepares the public-client authorization-code
flow with fresh state, nonce and PKCE S256, following the official
[registration and sign-in guide](https://developers.openai.com/siwc/token-sharing-open-source/sign-in).
The initial dynamic registration uses `dynamic_agent_client`; later sign-ins
reuse the saved issued client ID. The stable installation host ID is independent
of the selected Django or ChatGPT user. Issuer, signature, audience, expiry,
nonce, client identity and granted scopes are checked before credentials become
an eligible confirmation. Identity-only permission remains distinct from the
`resource.invoke` and `chatgpt.tokens.use.direct` plan scopes.

`assistant.connections.service` owns ten-minute, one-time, owner/session-bound
attempts, with at most five open attempts per owner. SQLite contains digests of
state and session binding; raw state, nonce, PKCE verifier and staged credentials
stay encrypted in the vault. A claimed or interrupted callback is not replayed.
Expiry/cancellation prevents final confirmation and clears pending secrets on
the corresponding lifecycle operation. Account selection is local metadata;
each Django user may have multiple registrations and at most one selected
connection. Settings and confirmation show the stable issued client ID beside
the account identity so registrations sharing an email remain distinguishable.
`ready` means the verified account granted plan permission. Model availability
still requires the separate inference gate and the selected account's catalogue.

The prepared refresh service serializes each connection's full read/refresh/write
sequence across threads and processes. It retains a rotated refresh token before
a waiting refresh proceeds; `invalid_grant` removes reusable credentials and
requires sign-in again. Network waits and filesystem lock acquisition occur
outside SQLite transactions. No scheduler or settings GET invokes refresh.
Disconnect clears reusable local tokens while retaining registration identity
for later sign-in. Remote revocation is attempted only when authorization is
enabled and a refresh token is present; failure is disclosed and local clearing
still proceeds. The UI directs the owner to review ChatGPT app access when
remote revocation was not confirmed. The
[accounts and sessions guide](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions)
is the upstream lifecycle reference.

### Private vault and recovery

`ASSISTANT_PRIVATE_DIR` defaults to `assistant-private` beside the configured
`db.sqlite3` (`TUXEDO_DATA_DIR/assistant-private`, or the project root's
`assistant-private` when no data directory is set). An explicit path selects
another private directory; changing it does not move existing files. Initialization
is an explicit lifecycle action, never a constructor or settings GET side effect.
The directory is `0700`; regular files are `0600`, owned by the application OS
user. Symlinks, hard-linked files, foreign ownership and unsafe reachable writable
ancestors are refused. The vault does not relax existing installation permissions.

The independent `vault.key` uses Fernet authenticated encryption and is never
derived from `SECRET_KEY`. A protected encrypted key check detects a wrong key;
each credential record is bound to its UUID and limited to 128 KiB of JSON.
Atomic ciphertext replacement preserves the prior record on a failed replace.
The protected `host-id` stores one persistent `urn:uuid:` UUIDv4 across restarts
and reauthorizations. POSIX permissions and `flock` are required: Linux, macOS
and Linux containers are the supported vault environments for this slice.
Native Windows vault operations fail closed; ordinary application imports and
unconnected pages remain available.

Back up the complete directory together with its database recovery point; a
database-only backup contains connection metadata but no usable credentials.
Keep the key, encrypted records and host ID together, protect/encrypt their
backup, and retain the application OS ownership and private modes on restore.
Do not commit, print, attach or copy the key/token material into diagnostics,
browser storage or settings forms. Application logging redacts callback queries
and credential fields; any additional server/proxy/access logging needs the same
protection before a later real validation.

Missing/wrong keys or a mismatched host fail closed. Never regenerate a key over
existing ciphertext or edit a stored host ID to bypass recovery checks. Restore
the matching complete backup; a missing key cannot be recovered from Django's
signing key. Restoring the directory preserves the original host identity and
is a recovery procedure, not a way to clone authorization to a second concurrent
installation. A new host requires its own identity and a separately reviewed
authorization. See [operations](../operations.md#assistant-data-and-integrations)
for the backup boundary.

<a id="eligibility-and-later-inference"></a>

### Eligibility and connected inference

[OpenAI's quickstart](https://developers.openai.com/siwc/quickstart) separates
identity scopes from plan permission. The
[plan-usage overview](https://developers.openai.com/siwc/token-sharing-open-source)
documents local/open-source clients and user/workspace-bound registrations;
paid or remotely hosted deployment has a separate access process. This
repository's PolyForm Noncommercial license is not proof of eligibility under
that program. The observed native authorization is bounded evidence for that
owner and installation, not a license/program eligibility guarantee. Later
[bounded streaming](../reviews/assistant-streaming-2026-10-19.md) and
[tool-response validation](../reviews/assistant-tool-response-2026-10-20.md)
record separate synthetic successes. Real Docker OAuth/inference, other
accounts/deployments, general model availability, limits/quotas and real token
refresh/revocation are not established by those observations.

[ChatGPT's user guide](https://learn.chatgpt.com/docs/sign-in-with-chatgpt)
describes eligible Plus/Pro users, shared existing usage limits and access
management. Plan permission grants neither ChatGPT conversations/memories nor a
new allowance. The gated adapter checks the account catalogue and sends only
the question, bounded recent history and necessary owned evidence, with targeted
reads/calculations when requested by the model's supported tools. Preserve
explicit unavailable/exhausted states without automatic paid fallback.

The current [preview contract](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations)
requires HTTP Responses requests with `store: false` and `stream: true`; HTTP
continuation does not provide persistent server conversation storage. A successful
synthetic request does not establish future quota, financial-answer quality or
instruction compliance. Streaming remains behind its own gate; validation
evidence belongs in dated reviews and cannot guarantee another installation's
live account access.

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
