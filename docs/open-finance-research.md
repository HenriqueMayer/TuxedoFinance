# Open Finance integration design

<a id="personal-open-finance-study"></a>

This guide records public provider documentation checked on **2026-10-18 and
2026-10-19** and the requirements for a future read-only integration. Provider
terms, prices, connectors and collection schedules can change; verify them
before selecting a service. The references do not establish live access or
complete resource coverage for a particular personal account.

Product availability belongs to the [roadmap](roadmap.md#personal-open-finance-study).
The [statement interface](apps/ingestion.md#interface-review-gate) remains paused.
The existing [Inter bill probe](open-finance-pilot.md) is a separate operator
command; it does not import records or enable a product bank connection.

## Access and consent

The [BCB Open Finance FAQ](https://www.bcb.gov.br/meubc/faqs/s/open-finance)
distinguishes regulated participants, customers sharing data and payment
initiation. Implementing published HTTP schemas does not make a local Django
application a participant. Free sharing for a bank customer also does not imply
free aggregation infrastructure.

Consent must identify the receiving institution, purpose, resources and period.
Authentication occurs through the bank, and consent can be revoked. The
[Open Finance Brasil data guide](https://openfinancebrasil.atlassian.net/wiki/spaces/OF/pages/17369300/Dados+Cadastrais+e+Transacionais+-+DC)
describes cancellation at either involved institution. Data access does not
authorize payments. Verify the exact regulated PF connector; direct connectors
can have different authentication, fields and privacy boundaries.

## Provider options

These are dated public descriptions, not a recommendation to buy or connect a
service. Supporting PF bank data does not prove that an individual can contract
the API. An MCP consultation product also does not automatically permit a local
backend to collect and retain records on a schedule.

| Route | Public source description | Requirements still to verify |
|---|---|---|
| Meu Pluggy | The [personal guide](https://docs.pluggy.ai/en/docs/guides/meu-pluggy-personal-use) describes free own-account access, up to five connections and 24-hour refresh without manual proxy refresh. | Exact card/bill fields, historical depth and personal-proxy endpoint coverage. It does not establish 6–8-hour collection. |
| Banco MCP / MCP.AI | [PF Plus](https://banco.mcp.ai/) and [terms](https://banco.mcp.ai/termos) describe personal use and REST access. The [connector list](https://banco.mcp.ai/todos-os-bancos) identifies Nubank, Inter and Mercado Pago PF Open Finance. | Bank collection cadence, scheduling rights, per-resource completeness, costs and retention/recovery commitments. |
| Belvo Panorama | The [consumer product](https://panorama.belvo.com/pt/) describes read-only financial consultation. Its [privacy policy](https://panorama.belvo.com/privacy-policy/) describes recurring refresh and processing on AWS in the United States. | Numeric refresh intervals, exact bank/resource coverage and permission for unattended local ingestion and retention. |
| Cumbuca Data MCP | The [product guide](https://www.cumbuca.com/ferramentas/open-finance-data-mcp) describes free own-CPF bank/card consultation, with one account at a time. | Multibank synchronization, scheduled collection and local import rights. |
| Pluggy commercial | The [Item guide](https://docs.pluggy.ai/en/docs/connections/item) describes provider-managed intraday scheduling; [pricing](https://www.pluggy.ai/precos) describes a commercial offer. | Personal contracting eligibility, actual interval/price and resource-specific cadence. The guide's 6/8-hour scheduling and premium 8/12/24-hour descriptions need clarification. |
| Belvo commercial API | The [recurring-link guide](https://developers.belvo.com/developer_resources/resources-links-overview) describes configurable refresh. The published [Launch offer](https://belvo.com/pt-br/planos-precos/) excludes personal use. | A distinct eligible contract would be required. Its coverage and cadence cannot be assumed for Panorama. |
| Klavi Conecte | The [institution list](https://docs.klavi.ai/connect/participant-institutions) includes relevant PF contexts; [API onboarding](https://docs.klavi.ai/connect/api-only) requires commercial contact and paid production. | Individual eligibility, price, resource coverage and outbound-only local delivery. |
| Polp / Celcoin | The [schedule](https://www.polp.com.br/docs/celcoin/sync-frequencies) describes intraday transaction collection, but [terms §11.1](https://polp.com.br/termos) exclude individual contracting. | PF data support does not remove that contracting restriction. |
| Lunch Flow | The [product guide](https://www.lunchflow.app/docs/guides/get-started/welcome) describes Brazil through Pluggy and daily synchronization. | It does not establish an intraday collection route. |

The dated sources do not establish one personal offer combining complete
multibank card/bill coverage, 6–8-hour bank collection and a local recovery
contract. Compare exact resources and terms before implementing an adapter.

## Coverage, cadence and history

The [Pluggy regulated coverage matrix](https://docs.pluggy.ai/en/docs/open-finance/institutions-coverage)
lists Nubank, Inter and Mercado Pago, but resource indicators combine personal
and business contexts. An institution-level indicator cannot certify a specific
PF account, card subtype, bill, installment or payment field. Preserve the
[regulated/direct distinction](https://docs.pluggy.ai/pt/docs/open-finance/overview)
and verify [counterpart coverage](https://docs.pluggy.ai/en/docs/open-finance/payment-data)
before matching transfers.

Keep the financial event date, bank publication time, provider collection time
and local retrieval time separate. A successful cached read or force-sync
request does not prove that the bank supplied new data. Pluggy's
[operational guide](https://docs.pluggy.ai/en/docs/open-finance/rate-limits)
distinguishes item updates, daily bills and less frequent detail/history reads:

| Resource | Dated documented collection behavior |
|---|---|
| Balances and recent bank transactions | Each item update, subject to availability and operational limits. |
| Card limits and recent card transactions | Each item update. |
| Bills and their transactions | Once daily. |
| Account/card details and older transactions | Initial collection and periodic collection, commonly every seven days. |

The [Klavi delay table](https://docs.klavi.ai/connect/rate-limits-and-throughput)
and [Polp schedule](https://www.polp.com.br/docs/celcoin/sync-frequencies) also
separate transaction freshness from daily invoices. Repeated local polling
cannot override bank/provider limits. An offline local process cannot promise
continuous retrieval.

The [transaction guide](https://docs.pluggy.ai/en/docs/products/transactions)
describes up to 12 months of initial history, not lifetime completeness. The
[card-cycle guide](https://docs.pluggy.ai/en/docs/products/credit-card-statement-cycle)
warns that transactions can be deleted and recreated under new IDs. Its
`providerId` is specific to regulated connectors. The
[installment guide](https://docs.pluggy.ai/en/docs/products/credit-card-installments)
describes absent bill IDs before publication and no universal purchase-group
identifier. Preserve partial history, pending/posted status and unknown dates.

## Daily card-bill pilot

The [Inter operator probe](open-finance-pilot.md) targets one closed bill through
the personal Meu Pluggy proxy. The [Pluggy changelog](https://docs.pluggy.ai/pt/changelog)
describes regulated Inter PF bill availability at closing. The
[bill product](https://docs.pluggy.ai/en/docs/products/credit-card-bills) and
[bill endpoint](https://v2.docs.pluggy.ai/pt/reference/bill/bills-list) describe
structured totals, due dates, charges and payments, rather than a bank-issued PDF.
General connector support does not guarantee all those fields through the free
proxy. Purchases require associated transaction evidence; unlinked open-card
activity cannot establish a final bill total.

Validate a published closed bill, its available purchases/installments, native
total, due date, charges and reported payments against the bank statement before
proposing reconciliation. Expand coverage only after verifying each connection.
Daily provider collection does not establish a local scheduler or reopen imports.

## Reconciliation design

Future adapters must use the application's [sources of truth](architecture.md#sources-of-truth)
and [ingestion preservation rules](apps/ingestion.md#duplicates-and-source-preservation).
Keep external observations separate from canonical financial sources and require
explicit reconciliation decisions before writing records.

| Evidence | Required accounting behavior |
|---|---|
| Income or expense | Match existing owned sources and movements first; create an unmatched source only after review. |
| Card purchase | Preserve spending/liability separately from the later cash settlement. |
| Bill payment in card and bank data | Link observations to one actual settlement; do not create a second expense. Preserve partial/excess payment amounts and dates. |
| Own transfer | Pair owned cash legs using amount, currency, date and counterpart evidence. Unmatched legs remain unresolved. |
| Manual entry, recurrence or installment | Preserve source links, category splits, schedule and notes. Similar descriptions do not establish identity. |
| Installments | Keep purchase date, index/total and billed period distinct; future installments are not current cash. |
| Refund, disappearance or changed ID | Retain prior observations and versions. Provider deletion does not authorize deleting a local source. |
| Fees, IOF or foreign purchase | Retain explicit native amounts, directions and supplied historical FX. Do not infer fees from differences or convert totals twice. |
| Missing baseline or incomplete history | Show the discrepancy. Never invent an opening balance, date, payment or purchase to force reconciliation. |

Retain scoped provider/institution/connection/resource IDs, source status/version,
native currency/amounts, event and collection times, local source links and
matching rationale. Exclude credentials and unnecessary identity fields. Define
retention/removal explicitly and test repeated reads, changed IDs, pending-to-posted
transitions, identical purchases, old restatements and incomplete responses.

## Local delivery and recovery

The [personal API guide](https://meu.pluggy.ai/api-guide) supports outgoing reads
of provider-collected data. Bank connections and data processing remain external
even when SQLite stays local. [Pluggy webhooks](https://docs.pluggy.ai/en/reference/webhooks)
and the [Banco MCP webhook guide](https://banco.mcp.ai/guias/webhook-quando-comprar-algo)
require public HTTPS receivers; a localhost callback is not such a receiver.
The Banco MCP guide describes one delivery attempt, a 15-second timeout and no
automatic retry. An outbound design must recover missed notices and old changes.

An adapter needs a strict query allowlist: Banco MCP's
[public collection](https://mcp.ai/openfinance/postman.json) also contains category
modification. Keep banking collection independent from model inference. Treat
provider labels and category guesses as untrusted evidence, validate ownership
and keep external waits outside SQLite transactions.

Expired/revoked consent, stale data and partial failures must remain visible.
Do not zero balances or erase records after collection failure. Revocation,
credential removal, provider-data deletion and local-evidence deletion are
separate operations. Review the complete processor chain and export/retention
rights, including [Banco MCP's policy](https://banco.mcp.ai/privacidade).
Bank consent, credential setup and financial confirmation each retain their own
explicit user action.

## Direct-bank API limits

[Inter's API help](https://ajuda.inter.co/conta-digital-pessoa-juridica/o-que-e-uma-api/)
restricts its direct offer to PJ, excluding PF/MEI. Nubank's
[Open Finance guide](https://nubank.com.br/nu/open-finance-nubank) describes
regulated institution-to-institution consent; it does not establish a public
personal developer API. Mercado Pago's
[developer terms](https://www.mercadopago.com.br/developers/pt/docs/resources/legal/terms-and-conditions)
admit individuals, and its [account-money reports](https://www.mercadopago.com.br/developers/pt/docs/reports/account-money/introduction)
describe balance movements. That partial source does not establish complete
issued-card purchases/bills or a multibank collection contract. Do not substitute
private app endpoints or reverse-engineered bank clients for a supported API.
