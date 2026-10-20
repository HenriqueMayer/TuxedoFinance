<a id="features-awaiting-redesign"></a>

# Paused features and planned integrations

Availability follows the current source checkout, not a scheduled release.
The developer version remains `0.10.0`; Unreleased preparation does not imply
publication or completion of the v1 acceptance/release process.

## Current milestone: validation hold

On **2026-10-19**, the owner paused further improvements to test the current
application before publishing the next version. Preserve the existing work and
installation data; keep the developer version unchanged during this hold.

The owner subsequently requested focused chat progress/Markdown, confirmed local
actions and Planning spacing fixes. These adjustments reopen only that scope;
Open Finance and other deferred work remain paused, and the publication hold stays.

On 2026-10-20, the owner also requested Markdown copying, default owned financial
consultations, canonical monthly simulations and reviewed transaction edits/deletion.
This focused assistant scope does not reopen Open Finance or publication.

- Await the owner's functional testing and acceptance feedback. Record findings
  before planning further adjustments; do not continue feature expansion now.
- Complete the applicable [release checks](versioning.md#preparing-a-release),
  including isolated application/browser, static-preview and Docker validation,
  before publication. Earlier focused checks do not establish release acceptance.
- Keep assistant extensions, financial news and the real Open Finance pilot as
  deferred roadmap work. A real bank connection is not a prerequisite for this
  release.
- Resume implementation or real bank setup only after the owner requests it.
  Publishing, merging, tagging and releasing still require explicit authorization
  after validation; this pause authorizes none of them.

## Paused interfaces

These features have no navigation entry or in-app roadmap page. Their retained
implementation remains suspended.

- **Net worth:** redesign the assets/debts presentation and explain what can
  and cannot be inferred from recorded history before exposing it again.
- **Statement imports:** simplify mapping, review and reconciliation. Existing
  posted transactions and owned read-only import provenance remain inspectable;
  upload, confirmation and undo are unavailable. Old operation URLs redirect
  to Transactions without executing a write.

Underlying net-worth calculations remain available to their other consumers.
The hidden net-worth URL returns to Dashboard. Moving a feature out of navigation
does not enable it or erase financial source records. The owner must validate
branch changes before authorizing any integration into `main` or publication.

<a id="assistant-foundation-and-later-provider"></a>

## Assistant and optional provider

The [assistant foundation](apps/assistant.md) provides local conversations and
bounded owned consultations, canonical monthly simulations and Markdown
presentation/copying. The implemented model catalogue/streaming path
is separately gated and defaults off; an unavailable composer never fabricates
responses. Six local changes have a separate user-confirmed execution path:
transaction creation, categorization, editing and deletion, goal creation and
category-budget creation. Other action interfaces remain proposals or future
work. See the
[confirmed action scope](assistant/actions.md).

The implemented [OpenAI authorization preparation](apps/assistant.md#openai-authorization-preparation)
adds owner-scoped account settings, a gated OAuth lifecycle and an encrypted
private vault. Real authorization is disabled by default; isolated mocks verify
the preparation, and [owner-approved native sign-in](reviews/assistant-native-sign-in-2026-10-19.md)
was observed through the original session's explicit local confirmation.
That server used process-only opt-in with `.env` unchanged; financial records
were preserved and no model listing, inference or financial export occurred.
Django authentication remains authoritative, and account linking cannot enable
the separate inference gate or a paid API-key fallback.

Later [bounded streaming](reviews/assistant-streaming-2026-10-19.md) and
[tool-response validation](reviews/assistant-tool-response-2026-10-20.md) record
separate synthetic successes. Real Docker OAuth/inference, broader eligibility,
general model availability/quotas and real token refresh/revocation are not
established by those observations.
The [gated provider](apps/assistant.md#provider-and-action-boundary) now implements
account-specific model selection, streaming, cancellation and local run history.
With either gate off it makes no external model request. A connected request
sends the question, bounded recent history and minimized page metadata;
targeted tools retrieve relevant owned records or run local calculations as
needed. The optional initial-page snapshot parameter does not restrict that
tool access. The assistant does not copy the whole database into each request.
Implemented transport does not establish live availability, allowance or model
quality; those require separate bounded evidence.
Automated assistance while the application is in use remains later work. There
is no daemon, unattended model invocation, payment, bank transfer or automatic
financial write. The six supported local changes always require the separate
reviewed confirmation and fresh server validation; chat text cannot confirm
them. Any later automation requires its own explicitly bounded rule and review.

## Financial news and external evidence

The [financial premises](assistant/financial-premises.md#future-news-consultation-preparation-only)
define the current Tuxedo persona and prerequisites for later on-demand news
consultation. Browsing/news retrieval is not implemented. The linked ChatGPT
account and plugins available to development agents do not automatically grant
it to this application. Validate subscription-specific tool eligibility, external
citations, freshness, private-query minimization, parsing/rendering and failure
behavior before enabling a provider. Keep local financial references, context
consent and financial execution separate. No paid fallback, new service,
scheduler or live inference is authorized by these written premises.

## Personal Open Finance study

The [2026-10-18 study](reviews/open-finance-personal-study-2026-10-18.md) examines
read-only import/reconciliation for one person's Nubank, Banco Inter and Mercado
Pago PF accounts, targeting collection every 6–8 hours. It finds no publicly
established personal production route meeting that target. The free personal
proxy is daily; intraday commercial eligibility is unverified and bill collection
has a separate daily cadence. At that stage, no provider had been selected or
configured.

The owner initially retained the 6–8-hour requirement on 2026-10-19. The
[intraday alternatives follow-up](reviews/open-finance-intraday-study-2026-10-19.md)
identifies Banco MCP as a conditional personal REST candidate with the three
listed PF connectors, and Belvo Panorama as a separate personal MCP lead. Neither
has a publicly established complete intraday contract for this scope. Keep
per-resource bank collection distinct from local API polling. Resolve eligibility,
cadence, coverage and local recovery before selecting or connecting a provider.

Later on the same date, the owner accepted **daily updates for a bill-only pilot**.
The [pilot decision and bank evidence](reviews/open-finance-intraday-study-2026-10-19.md#daily-card-bill-pilot--subsequent-owner-decision)
prioritize investigating the free Meu Pluggy personal route, with Inter PF as the
proposed first card and Nubank/Mercado Pago subject to separate resource verification.
This is a scoped cadence exception, not acceptance of daily updates for broader
aggregation or proof that the personal proxy returns complete bills. Start with
synthetic read-only preparation; real consent and financial confirmation remain
separate decisions.

The [operator-only pilot command](open-finance-pilot.md) is implemented with an
offline synthetic mode, explicit live read, one-shot hidden credentials and private
daily observation reuse. It performs no database queries or financial writes and
does not reopen ingestion routes. Inter origin is operator-attested because the
personal proxy does not document the original bank. Real bank consent, proxy bill
availability and comparison with an actual statement have not been exercised.

**Pilot continuation is deferred during the validation hold.** Before resuming
real setup, review the receiving institution, actual permission groups, provider
cloud processing and revocation/deletion behavior with the owner, following the
[consent and privacy guide](open-finance-pilot.md#before-authorizing-real-bank-data).
Then verify free-route bill availability, daily freshness and completeness
against the Inter statement. No bank authorization or credential collection is
pending execution during this pause.

Coverage per PF resource, actual cost, consent/revocation, historical completeness,
identifier changes and local delivery remain acceptance gates. This research
does not re-enable CSV/OFX ingestion or authorize real accounts, credentials,
commercial contact, payment initiation or automatic ledger confirmation.
Cloud hosting remains a separate study covering privacy and deployment security.
