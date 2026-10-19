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
bounded, read-only owned context. No provider is connected; the composer remains
unavailable and no model response or financial execution is fabricated.
Provider streaming/cancellation and action/simulation interfaces are preparation
only, with no action execution endpoint.

The next planned provider is an explicit Sign in with ChatGPT connection linked
to the current Django user, subject to the official local-app flow and account
eligibility. It does not replace local authentication or introduce paid API-key
fallback. Actual OAuth, token storage, model calls and any external financial
context require their separately approved implementation and validation.
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
