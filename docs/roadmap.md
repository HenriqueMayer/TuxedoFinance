<a id="features-awaiting-redesign"></a>

# Paused features and planned integrations

Availability follows the current source checkout and its feature gates.
Merge and Docker publication of version `0.11.0` were explicitly authorized
on **2026-10-21**. The [release PR](https://github.com/HenriqueMayer/TuxedoFinance/pull/36)
records exact-revision validation and distribution status.
Delivered behavior belongs in the
[app guides](README.md#per-app-reference); dated evidence belongs in the
[review index](reviews/README.md).

<a id="current-milestone-validation-hold"></a>

## Current milestone: release 0.11.0

The owner paused broader improvements on **2026-10-19**, then explicitly
authorized committing the completed work, merging into `main` and publishing
the Docker release on **2026-10-21**. This release decision does not reopen
deferred integrations or establish completion of every manual acceptance item.

- Complete the applicable [release checks](versioning.md#preparing-a-release),
  including isolated application/browser, preview and Docker validation. Record
  exact-revision results and remaining manual checks before publication;
  historical successes do not establish this candidate's validation status.
- Preserve installation data and supported upgrades. Record further owner
  testing feedback without marking unperformed walkthrough items complete.
- Resume deferred implementation or real bank setup only after an owner request.
  A bank connection is not a release prerequisite or part of this authorization.

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
  real token refresh/revocation and Docker OAuth/inference remain unverified
  beyond the specific observations in the [review archive](reviews/README.md).

Keep Django ownership, local storage and minimized external context. Reads and
simulations need no extra execution confirmation; financial writes retain their
separate reviewed confirmation and fresh server validation. Future automation
requires an explicit bounded rule; ordinary chat text cannot confirm a write.

## Financial news and external evidence

Browsing and financial-news retrieval are unavailable. A linked ChatGPT account
or development-agent plugin does not grant these tools to the application.
The [financial premises](assistant/financial-premises.md#future-news-consultation-preparation-only)
define future acceptance: provider eligibility, verifiable citations, freshness,
private-query minimization, safe rendering and failure behavior. Keep external
evidence, context consent and financial execution separate. These premises do
not authorize live inference, paid fallback, a new service or a scheduler.

## Personal Open Finance study

The broader target remains **Nubank, Banco Inter and Mercado Pago PF every 6–8
hours**. The [personal study](reviews/open-finance-personal-study-2026-10-18.md)
and [intraday follow-up](reviews/open-finance-intraday-study-2026-10-19.md) do not
establish a complete personal production route meeting it. Resolve eligibility,
cost, per-resource coverage/cadence, history and local recovery before selection;
local API polling is not proof of fresh bank collection.

The owner accepted a separate **free Meu Pluggy, Inter PF card-bill pilot with
daily updates**. This [24-hour exception](reviews/open-finance-intraday-study-2026-10-19.md#daily-card-bill-pilot--subsequent-owner-decision)
does not change the broader target or establish complete proxy bill coverage.
The [operator-only command](open-finance-pilot.md) already supports offline
synthetic evidence and an explicit live read with private daily observation
reuse. It makes no application database queries or financial writes and does not
reopen imports. Inter origin is operator-attested; real consent, bill coverage
and comparison with an actual statement remain unexercised.

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
