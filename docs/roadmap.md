<a id="features-awaiting-redesign"></a>

# Paused features and planned integrations

Availability follows the current source checkout, not a scheduled release.
The developer version remains `0.10.0`; Unreleased preparation does not imply
publication or completion of the v1 acceptance/release process.

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

## Assistant foundation and later provider

The [assistant foundation](apps/assistant.md) provides local conversations and
bounded, read-only owned context. The implemented model catalogue/streaming path
is separately gated and defaults off; an unavailable composer never fabricates
responses. Action/simulation interfaces remain contracts with no execution endpoint.

The implemented [OpenAI authorization preparation](apps/assistant.md#openai-authorization-preparation)
adds owner-scoped account settings, a gated OAuth lifecycle and an encrypted
private vault. Real authorization is disabled by default; isolated mocks verify
the preparation, and [owner-approved native sign-in](reviews/assistant-native-sign-in-2026-10-19.md)
was observed through the original session's explicit local confirmation.
That server used process-only opt-in with `.env` unchanged; financial records
were preserved and no model listing, inference or financial export occurred.
Django authentication remains authoritative, and account linking cannot enable
the separate inference gate or a paid API-key fallback.

Real Docker OAuth, broader license/program eligibility, model access and
limits/quotas, streaming, and real token refresh/revocation remain unverified.
The [gated provider](apps/assistant.md#provider-and-action-boundary) now implements
account-specific model selection, streaming, cancellation and local run history.
With either gate off it makes no external model request. Financial context is
unchecked by default and included only for an explicitly selected request.
Implemented transport does not establish live availability, allowance or model
quality; those require separate bounded evidence.
Opt-in assistance while the application is in use is later work; no daemon,
unattended automation or financial writes are enabled. Later goals, budgets,
alerts and transaction creation/categorization may use previously enabled
bounded rules where supported; otherwise they require the applicable explicit
review decision. Fresh server validation always applies.

## Personal Open Finance study

The [2026-10-18 study](reviews/open-finance-personal-study-2026-10-18.md) examines
read-only import/reconciliation for one person's Nubank, Banco Inter and Mercado
Pago PF accounts, targeting collection every 6–8 hours. It finds no publicly
established personal production route meeting that target. The free personal
proxy is daily; intraday commercial eligibility is unverified and bill collection
has a separate daily cadence. No provider is selected or configured.

Coverage per PF resource, actual cost, consent/revocation, historical completeness,
identifier changes and local delivery remain acceptance gates. This research
does not re-enable CSV/OFX ingestion or authorize real accounts, credentials,
commercial contact, payment initiation or automatic ledger confirmation.
Cloud hosting remains a separate study covering privacy and deployment security.
