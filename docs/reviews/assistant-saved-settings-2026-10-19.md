# Saved assistant settings and gear — 2026-10-19

## Scope

The owner requested remembering the most recent model/reasoning effort and
correcting the distorted chat settings icon after approving the compact layout.
Current contracts live in the [assistant guide](../apps/assistant.md#saved-chat-settings),
[navigation guide](../frontend/navigation.md#assistant-panel) and
[interface map](../interface-map.md). Earlier uncommitted work is preserved.

## Delivery

The current owned `ProviderConnection` stores `last_model_slug` and
`last_reasoning_effort`. Explicit native select changes save only the pair and
connection ID through authenticated CSRF-protected POST. The server rejects
extra fields, another/inactive account, unavailable capabilities and unsupported
pairs. Saving does not generate a message, copy financial context, enable a
provider or change the connection's credential/catalogue timestamp.

Reload, Close/reopen and New conversation restore only the last catalogue-valid
pair for that user/account. No invented fallback replaces a removed model;
removed effort falls back to Model default for a still-available model. Initial
empty choices, explicit clearing and bound POST recovery remain. Accepted Send
also persists the pair, including without JavaScript; redirects/completion GETs
omit stale model/effort query parameters. Browser memory serializes pending
saves, chat reloads wait for them, and failures expose retry without discarding
the draft. Context permission remains per request and unchecked on a fresh
composer. No browser storage contains settings or unsent chat text.
Restoring after a same-user linked-account switch keeps unsent text but takes
model/effort and unchecked consent from the fresh account response. A preference
storage failure returns structured recovery; failure of the optional preference
write after an accepted Send cannot strand or abort its generation.

The old transformed/asymmetric gear outline is replaced by the standard
design-system settings artwork, with an untransformed centered inner circle.
Its SVG is a non-shrinking 16px square inside the unchanged 44px target.
The approved Tuxedo mark and artwork motion are unchanged. The Design Lab uses
the same gear and retains only synthetic page-memory choices; reload clears its
demonstration state.

## Installation preservation

Applied only additive migration `assistant.0005_providerconnection_chat_preferences`
to the existing local SQLite installation after a private SQLite backup.
Integrity checks passed before/after. Row counts and hashes of all pre-existing
columns remained identical across 45 application tables; the migration ledger
is excluded because recording the new migration is expected.
Evidence is under ignored
`.local/backups/assistant-preferences-20261019T181256Z/`.
No `.env`, credential vault, financial record, conversation or message was edited
by this migration. No historical model preference was inferred or seeded.

## Validation

Fresh isolated Django assistant suite: **216 passed**, including 18 saved
settings cases and explicit preference-storage failure recovery. Django system
checks, migration drift and assistant executable
correctness lint passed. Frontend tooling: **16 passed**. CSS and Brazilian
Portuguese translations rebuilt from source.

The frozen feature/browser check passed **76 distinct scenarios**: 47 guarded
chat/stream/window/Design Lab cases and 29 local-chat/connection cases. This
includes keyboard selection, reload, New, Close/reopen, delayed saves with HTMX,
failed save/retry, native Send, owned-account switching, both themes/languages,
desktop and 390px/320px phone layouts, reduced motion and no-JavaScript paths.
The initial navigation assertion expected an HTMX header intentionally suppressed
by this repository; it now verifies the actual XHR navigation instead.

Final rendered inspection found the added Saved confirmation could be clipped
by the former 280px popup cap. Only that cap changed to 340px, still constrained
by available panel height; short viewports retain internal scrolling. The six
settings/theme/viewport scenarios passed again with explicit Saved-content
bounds against those rebuilt final CSS assets. The acknowledgement is fully
inside the popup on desktop and 390px phones in both themes; short 320px views
retain usable focus, controls and internal scrolling.

Browser checks use disposable databases, loopback servers and synthetic
providers; they do not access the developer database or consume the linked
subscription. Evidence is under ignored
`.local/test-results/assistant-settings-preferences-20261019/`;
source fingerprints are under `.local/runtime/assistant-settings-preferences-20261019/`.
The local service still responds on loopback after the additive migration.

## Limits

No real model call, paid API fallback, financial calculation change, account
reconnection, commit or publication. Phone checks emulate viewport/touch; they
do not establish physical handset software-keyboard behavior. The complete
financial-application browser suite is outside this scoped assistant increment.
Saving is asynchronous: a native browser reload before Saved confirmation can
discard a queued, unconfirmed change. Chat Close/reopen, New and HTMX loads wait
for the bounded queue; pending changes are not written to browser storage.
