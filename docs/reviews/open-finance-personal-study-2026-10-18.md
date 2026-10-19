# Personal Open Finance feasibility — 2026-10-18

**Status:** Public-source study; no bank integration is implemented or enabled.
**Confirmed use:** One person's Brazilian PF accounts at Nubank, Banco Inter
and Mercado Pago; import and reconciliation only, with a target refresh every
6–8 hours. Payment initiation is excluded.
**Source verification:** 2026-10-18. Vendor coverage, terms and prices can change.

The [roadmap](../roadmap.md) owns present availability. The existing
[statement-ingestion interface](../apps/ingestion.md#interface-review-gate)
remains paused, including confirmation and undo. This study neither bypasses
that gate nor authorizes financial writes, accounts, credentials, commercial
contact or use of real banking data. No such activity was performed for it.

## Finding and decision boundary

The checked public sources do **not** establish an available personal PF
subscription that satisfies the 6–8-hour target for these three institutions.
The free MeuPluggy route is explicitly personal but refreshes every 24 hours.
Commercial autosync exists, but its availability to an individual reading only
their own accounts is unproven. Even commercial intraday synchronization does
not mean that every resource refreshes intraday: bills have a daily cadence.

Keep the integration planned. Before selecting a provider, establish personal
eligibility, exact PF resource coverage, cadence and recovery commitments, total
cost and the local application's delivery architecture. An advertised connector
or a successful sandbox does not prove these production conditions.

## Access, consent and payment boundaries

The [BCB Open Finance FAQ](https://www.bcb.gov.br/meubc/faqs/s/open-finance)
limits direct participation to institutions authorized by the BCB. A personal
Django installation cannot become a participant merely by implementing the
published HTTP schemas. A provider/participant arrangement is therefore the
practical integration route to investigate. Free sharing for the bank's customer
does not imply free aggregation infrastructure.

The same FAQ distinguishes data sharing from payment initiation. Reading a
record of a Pix or transfer does not authorize sending money. Consent identifies
the institutions and authorized data/services, requires the customer's bank
authentication and can be revoked. A new bank requires its own authorization.
The [Open Finance Brasil customer-data guide](https://openfinancebrasil.atlassian.net/wiki/spaces/OF/pages/17369300/Dados+Cadastrais+e+Transacionais+-+DC)
also requires a defined purpose and period, with cancellation at either involved
institution. Do not assume indefinite access or a universal consent duration.

## Institution and resource matrix

The [Pluggy regulated coverage matrix](https://docs.pluggy.ai/en/docs/open-finance/institutions-coverage)
lists all three institutions with Personal and Business contexts. Its resource
indicators are explicitly the **union across contexts**. A green indicator is
not proof that a particular PF connector supplies that resource. No authenticated
connector lookup or real consent was used to resolve that limitation.

| Institution | Accounts/balances | Bank transactions | Card purchases and installments | Bills/payments | Own-transfer evidence |
|---|---|---|---|---|---|
| Nubank | Listed in the institution-level matrix; exact PF fields unverified. | Listed; exact PF history and completeness unverified. | Credit cards listed; PF sub-products and fields unverified. | Vendor bill product exists; this PF connection unverified. | Bank transactions may supply Pix/transfer metadata; exact counterpart coverage unverified. |
| Banco Inter | Listed in the institution-level matrix; exact PF fields unverified. | Listed; exact PF history and completeness unverified. | Credit cards listed; PF sub-products and fields unverified. | Vendor bill product exists; this PF connection unverified. | Bank transactions may supply Pix/transfer metadata; exact counterpart coverage unverified. |
| Mercado Pago | Listed in the institution-level matrix; exact PF fields unverified. | Listed; exact PF history and completeness unverified. | Credit cards listed; PF sub-products and fields unverified. | Vendor bill product exists; this PF connection unverified. | Bank transactions may supply Pix/transfer metadata; exact counterpart coverage unverified. |

The vendor's [Open Finance overview](https://docs.pluggy.ai/pt/docs/open-finance/overview)
separates regulated and direct connectors. Do not substitute its direct-connector
tables for regulated PF coverage: those are different integrations and can expose
different fields. The [payment-data coverage guide](https://docs.pluggy.ai/en/docs/open-finance/payment-data)
also distinguishes operation/direction-specific counterpart coverage. A displayed
bank name alone is insufficient evidence for automatic transfer matching.

## Eligibility, cost and cadence

| Route | Publicly established position | Consequence for this study |
|---|---|---|
| Meu Pluggy / MeuPluggy proxy | [Personal guide](https://docs.pluggy.ai/en/docs/guides/meu-pluggy-personal-use): free own-account use, up to five connections, no commercial use or business due diligence. Updates every 24 hours; proxy items cannot be refreshed manually. | Fits the personal identity boundary and three requested banks in principle; does not meet 6–8 hours. Exact resource coverage remains unverified. |
| Pluggy commercial data | [Pricing](https://www.pluggy.ai/precos): starts at R$2,500/month with included volume and request-based excess. Public material directs companies/products to commercial onboarding and personal users to Meu Pluggy. | No public confirmation that this personal-only use can contract intraday production access, or what its actual total price would be. |
| Belvo | [Pricing](https://belvo.com/pt-br/planos-precos/): Launch is R$1,500/month for specified business segments; personal use is not served. Sandbox access is free for evaluation; production requires a paid plan. | Its public offer does not provide the requested personal production route. No exception was requested or assumed. |

The [Pluggy Item guide](https://docs.pluggy.ai/en/docs/connections/item)
contains two cadence descriptions: its scheduling section lists intervals
including 6, 8, 12 and 24 hours or up to four scheduled daily windows, while its
premium notice lists 24, 12 or 8 hours depending on subscription. Configuration
is provider-managed. Treat that discrepancy as unresolved, not a promise of a
6-hour plan. The guide describes `nextAutoSyncAt` as an earliest execution time,
subject to delay, and specifically directs individuals reading their own accounts
to the daily MeuPluggy path. It does not establish a personal intraday SLA.

| Resource | Documented collection behavior, subject to consent and availability |
|---|---|
| Account balance and recent bank transactions | Collected on each item update. |
| Card limits and recent card transactions | Collected on each item update. |
| Bills and transactions belonging to bills | Collected once per day. |
| Account/card lists, details and older transactions | Initial collection and periodic collection, commonly every seven days. |

These cadences come from the [operational-limit guide](https://docs.pluggy.ai/en/docs/open-finance/rate-limits).
It describes limits by CPF/CNPJ, institution and product, and warns that duplicate
connections consume limits faster. Querying already-collected vendor data more
often does not force a new bank collection. A local timer must not try to defeat
provider synchronization or operational limits.

## History, identifiers and card lifecycle

The [transaction product](https://docs.pluggy.ai/en/docs/products/transactions)
describes up to 12 months of initial data, not complete lifetime history.
It distinguishes pending and posted entries, bank and card directions, transfer
metadata and optional bill associations. Pending card transactions can represent
open bills or future installments. Treat history availability, original purchase
dates, date-only versus timestamp meaning and pending transitions as explicit
sample checks for each PF bank; never overwrite an existing local baseline with
a fetched partial history.

The [card-cycle guide](https://docs.pluggy.ai/en/docs/products/credit-card-statement-cycle)
warns that a provider transaction can be deleted and recreated with a new Pluggy
ID during a statement transition. Its `providerId` is available only through
regulated connectors; direct connections do not provide it. There is no general
old-to-new replacement link. An external row ID is therefore provenance, not an
unconditional permanent accounting identity. Verify what the personal proxy
preserves before relying on upstream IDs.

The [installment guide](https://docs.pluggy.ai/en/docs/products/credit-card-installments)
describes absent bill IDs before a bill is available and no unique identifier
grouping all installments of a purchase. The [bill product](https://docs.pluggy.ai/en/docs/products/credit-card-bills)
includes totals, due dates, finance charges and payment records, subject to the
connection. Neither a bill's existence nor a local automatic `PAID` status alone
proves that a bank payment was actually made.

## Reconciliation design for a later implementation

The following is a proposed review contract, **not implemented provider import
behavior**. Reuse the [existing sources of truth](../architecture.md#sources-of-truth)
and [ingestion preservation rules](../apps/ingestion.md#duplicates-and-source-preservation).
Retain bank evidence separately before suggesting a canonical financial action.

| Evidence or conflict | Required review and accounting boundary |
|---|---|
| Bank income/expense | Match an existing owned movement first. Only an explicit unmatched decision may create one categorized source and its ordinary settlement. |
| Credit-card purchase | Reconcile with the existing card transaction/invoice item. A purchase affects spending and liability, not purchase-date bank cash. |
| Paid bill appearing in card and bank data | Link both observations to one settlement. Match an existing automatic debit or, after deliberate manual-settlement review, record the actual-date payment; never add the bill payment as a second expense. |
| Partial or excess bill payment | Preserve each actual amount/date and card credit. A total or status cannot replace individual confirmed payments. |
| Transfer between owned accounts | Pair the two owned cash legs using strong evidence, amount/currency/date and counterpart context. Preserve unmatched legs for review; never classify both as income/expense or infer the counterpart from a similar description. |
| Existing manual transaction, recurrence or installment | Match its source/movement and preserve category splits, schedule and notes. Do not reconstruct a recurring template from repeated statement text or create another source for each synchronization. |
| Installments | Keep the original economic purchase, installment index/total and billed period distinct. Do not sum future installments into today's cash or group purchases using description alone. |
| Reversal, refund or disappearance | Preserve the earlier observation and relationship. A temporary provider deletion is not authority to delete a local financial source; distinguish a real reversal from missing data and request review. |
| Changed/reused external ID or pending-to-posted transition | Use scoped identities, versions and idempotent reconciliation. Weak date/amount/description matches remain suggestions, especially for identical same-day purchases. |
| Fees, interest, IOF and foreign purchases | Keep explicit amount, currency, direction, original amount and bank-applied FX when supplied. Do not infer fees from a difference, convert card totals twice or replace persisted historical FX with a current rate. |
| Opening/closing discrepancy or incomplete history | Show a dated discrepancy and missing baseline. Never manufacture an opening date, balance adjustment, payment or historical purchase to force equality. |

Each observation should retain provider, institution/context, connection/account,
resource and external identifiers, source status/version, native amounts and
currencies, source dates/timestamps, collection time and any available raw-field
provenance. Keep the local source link, matching rationale and owner's decision
separate. Do not retain credentials, tokens or unnecessary identity fields in
financial evidence. A later design must define retention and removal explicitly;
this study creates no schema or immutable-audit promise.

## Local operation, revocation and recovery

The [personal API guide](https://meu.pluggy.ai/api-guide) describes local clients
reading collected data through outgoing API calls. The application's SQLite
ledger can remain local, but the provider still handles the bank connection and
financial data; this is not an entirely offline data path.

[Pluggy webhooks](https://docs.pluggy.ai/en/reference/webhooks) require an HTTPS
receiver and reject `localhost`. A browser authorization return and a
server-to-server event receiver are different endpoints. A future design must
choose between an explicitly approved public receiver/relay and a documented
outgoing reconciliation strategy. Re-reading a narrow recent-date window alone
can miss older card restatements. An offline local application also cannot claim
continuous collection or delivery guarantees without a separate runtime decision.

Expired/revoked consent, bank authorization requests, offline connectors and
stale/partial results must remain visible. Reauthorization must be deliberate;
failed collection must not zero balances or erase sources. Separate stopping
future collection, removing local credentials, deleting provider-held data and
deleting local evidence: revocation must not be advertised as performing all four.
Do not keep using a cancelled authorization or add payment scopes to data consent.

## Evidence needed before another implementation decision

1. Public terms or subsequently authorized confirmation that the actual PF owner
   can obtain intraday production data, including applicable price and limits.
2. Per-bank PF samples for accounts, recent/history transactions, cards, bills,
   partial/full payments, installments, refunds, transfer counterparts and IDs.
3. Cadence per resource, acceptable staleness, consent renewal, outage/retry
   behavior and a delivery design compatible with the approved local runtime.
4. A disposable synthetic/sandbox reconciliation proof with repeated syncs,
   changed/deleted IDs and existing manual records, before any real-bank trial.
5. Separate approval for credentials, actual account consent, external processing
   and financial confirmation; completing this study grants none of these.

## Validation record

This document records source research and a proposed reconciliation contract.
It contains no live-bank, provider-account or model validation results. Final
repository documentation checks and assistant-base validation belong in the
implementation's dated validation record after they have actually run.
