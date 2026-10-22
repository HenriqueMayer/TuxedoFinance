<a id="features-awaiting-redesign"></a>

# Paused features and planned integrations

Availability follows the current source checkout and its feature gates.
Delivered behavior belongs in the [app guides](README.md#per-app-reference).
Use the matching [release](https://github.com/HenriqueMayer/TuxedoFinance/releases)
for published version and distribution status.

<a id="current-milestone-validation-hold"></a>

## Release validation

The [release workflow](versioning.md#preparing-a-release) requires isolated
application/browser, preview and Docker validation for the exact candidate.
Preserve installation data and supported upgrades. Record remaining manual
checks separately; a release does not enable paused integrations or establish
provider eligibility. A real bank connection is not a release prerequisite.

## Paused interfaces

These retained features have no navigation entry and remain gated:

- **Net worth:** redesign the assets/debts presentation and explain what can
  and cannot be inferred from recorded history before exposing it again.
- **CSV/OFX statement imports:** simplify mapping, review and reconciliation
  before reopening upload, confirmation or undo. Existing posted records and
  owned read-only provenance remain inspectable. See the
  [ingestion gate](apps/ingestion.md#interface-review-gate).

Net-worth calculations remain available to other consumers. Old net-worth URLs
return to Dashboard; paused import operations return to Transactions before
executing. These gates preserve financial source records.

<a id="assistant-foundation-and-later-provider"></a>

## Assistant and optional provider

The delivered [assistant](apps/assistant.md) includes local chat, gated ChatGPT
authorization/streaming, owned consultations, canonical simulations and Markdown
presentation/copying. Six [confirmed local actions](assistant/actions.md) are
implemented: transaction creation, categorization, editing and deletion, goal
creation and category-budget creation. They are not pending roadmap work.

Future work, requiring a separately agreed scope:

- Extend provider-neutral contracts to optional API keys or custom endpoints.
  No such configuration or automatic paid fallback is implemented or authorized.
- Evaluate additional actions and opt-in assistance during application use.
  Define explicit triggers, limits, cancellation, duplicate prevention and audit
  results before execution. No automation rule, unattended invocation, payment,
  bank transfer or automatic financial write is currently enabled.
- Gather bounded evidence for financial-answer quality and malicious-record
  handling. Broader account/deployment eligibility, model availability/quotas,
  real token refresh/revocation and Docker OAuth/inference need validation for
  each intended account and installation.

Keep Django ownership, local storage and minimized external context. Reads and
simulations need no extra execution confirmation; financial writes retain their
separate reviewed confirmation and fresh server validation. Future automation
requires an explicit bounded rule; ordinary chat text cannot confirm a write.

## Financial news and external evidence

Browsing and financial-news retrieval are unavailable. A linked ChatGPT account
does not grant these tools to the application.
The [financial premises](assistant/financial-premises.md#future-news-consultation-preparation-only)
define future acceptance: provider eligibility, verifiable citations, freshness,
private-query minimization, safe rendering and failure behavior. Keep external
evidence, context consent and financial execution separate. These premises do
not authorize live inference, paid fallback, a new service or a scheduler.

## Personal Open Finance study

Future PF aggregation must establish provider eligibility, exact resource
coverage, cadence, history, cost and local recovery before selection. The
[Open Finance research](open-finance-research.md) compares public provider
options and source-preserving reconciliation. Local API polling is not proof
of fresh bank collection.

The [operator-only command](open-finance-pilot.md) supports a narrower Meu Pluggy
Inter card-bill pilot with daily private observations. It provides offline
synthetic evidence and an explicit live read, with no application database
queries, financial writes or reopening of imports. Inter origin is operator-
attested. Real consent, bill coverage and statement reconciliation must be
verified before relying on a live observation.

**Real setup and pilot continuation are paused.** No bank authorization or
credential collection is pending execution. On a future owner request, first
review receiving institutions, actual permissions, cloud processing and
revocation/deletion through the [consent and privacy guide](open-finance-pilot.md#before-authorizing-real-bank-data).
Then verify free-route availability, daily freshness, historical completeness
and reconciliation against the Inter statement, including existing manual
records, purchases/payment duplication, installments, refunds and changed IDs.

Research does not authorize bank connections, credentials, commercial contact,
payment initiation or automatic ledger confirmation. Cloud hosting remains a
separate privacy and deployment-security study.
