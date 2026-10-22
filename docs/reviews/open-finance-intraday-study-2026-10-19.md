# Personal intraday Open Finance alternatives — 2026-10-19

**Status:** Public-source feasibility follow-up; no provider selected or enabled.
**Owner decisions:** Initially retain the 6–8-hour target for broader aggregation.
Later on the same date, accept daily collection for a narrower credit-card-bill
pilot, as recorded below. The broader intraday requirement is not withdrawn.
Scope remains one person's PF accounts at Nubank, Banco Inter and Mercado Pago,
with read-only collection and reconciliation.
**Verification date:** 2026-10-19. Prices, terms and connector lists are observations,
not quotations or proof of live account availability.

This extends the [initial study](open-finance-personal-study-2026-10-18.md),
including its source-preserving accounting and consent boundaries. The
[roadmap](../roadmap.md#personal-open-finance-study) owns present availability.
Research does not reopen [paused statement operations](../apps/ingestion.md#interface-review-gate),
authorize a purchase, commercial contact, account consent or financial writes.

## Finding and recommended direction

**For broader intraday aggregation, Banco MCP is the strongest personal API
candidate found, but its bank-refresh cadence remains unproven.** Its public
offer establishes a personal plan, REST
access and listed PF Open Finance connectors for the requested institutions.
That is materially more useful than an assistant-only connector, but does not
yet establish the complete 6–8-hour requirement.

No reviewed route currently proves the combination of individual eligibility,
all three banks, required card/bill resources, intraday collection and a complete
local delivery/recovery contract. This is a bounded research conclusion, not a
claim that no suitable contract can exist. Prioritize the unresolved Banco MCP
questions below; retain Belvo Panorama as a secondary personal research candidate.
Do not silently substitute a daily refresh or a single-bank chat demonstration.
The subsequent bill-only daily pilot is a separately accepted scope below.

The [BCB FAQ](https://www.bcb.gov.br/meubc/faqs/s/open-finance)
continues to distinguish regulated participants from customers authorizing data
sharing. Public banking schemas alone do not give this Django application direct
participant access. A provider's support for PF **data** is also distinct from
allowing a PF **customer** to contract its API.

## Candidate comparison

| Route | Public evidence checked | Decision for the confirmed personal scope |
|---|---|---|
| Banco MCP / MCP.AI | [PF Plus](https://banco.mcp.ai/) advertises R$29.90/month, three banks and REST; [terms](https://banco.mcp.ai/termos) permit personal use. | First candidate for clarification. No documented 6–8-hour collection allowance or commitment found; resource completeness still needs verification. |
| Belvo Panorama / Belvo MCP | [Personal product](https://panorama.belvo.com/pt/) advertises free read-only access and multiple connected sources. | Relevant personal alternative; numeric refresh frequency, exact three-bank coverage and permission for unattended local ingestion remain unverified. |
| Cumbuca Open Finance Data MCP | [Official product](https://www.cumbuca.com/ferramentas/open-finance-data-mcp) is free for the owner's CPF, with bank/card consultation and one account at a time; multiple banks remain planned. | Does not establish the requested multibank synchronization. On-demand consultation is not an intraday import contract. |
| Meu Pluggy | [Personal guide](https://docs.pluggy.ai/en/docs/guides/meu-pluggy-personal-use) permits own-account use, up to five connections, but refreshes every 24 hours without manual proxy refresh. | Fails the retained cadence requirement. More frequent local reads cannot refresh its underlying bank data. |
| Pluggy commercial | [Item guide](https://docs.pluggy.ai/en/docs/connections/item) describes provider-managed intraday scheduling, with differing 6/8-hour and premium 8/12/24-hour descriptions. | Individual production eligibility, actual cadence/price and resource coverage are not established. Do not assume a developer account or paid plan resolves them. |
| Belvo commercial API | [General recurring-link guide](https://developers.belvo.com/developer_resources/resources-links-overview) documents a configurable 6-hour interval; [Launch pricing](https://belvo.com/pt-br/planos-precos/) starts at R$1,500/month and explicitly excludes personal use. | Exclude the published Launch offer. General link refresh does not prove regulated OFDA or Panorama cadence; no exceptional personal commercial arrangement or cadence-specific charge was established. |
| Klavi Conecte | [Institution list](https://docs.klavi.ai/connect/participant-institutions) includes the three banks in personal contexts; [onboarding](https://docs.klavi.ai/connect/api-only) requires commercial contact and paid production. | Technically relevant, but individual eligibility, price and an outbound-only local delivery arrangement remain unproven. Its resource-delay table is discussed below. |
| Polp / Celcoin | [Synchronization schedule](https://www.polp.com.br/docs/celcoin/sync-frequencies) is intraday for recent account/card transactions; [terms §11.1](https://polp.com.br/termos) explicitly reject individual contracting. | Excluded for the present PF contracting scope, despite supporting PF bank data. Opening a company is not an approved workaround. |
| Lunch Flow | [Product guide](https://www.lunchflow.app/docs/guides/get-started/welcome) documents Brazil through Pluggy and daily automatic synchronization. | Does not establish the required intraday route. |

Secondary enterprise leads did not establish a usable personal offer:
[Celcoin Financial Data](https://www.celcoin.com.br/open-finance/financial-data/),
[Lina](https://linaopenx.com.br/) and [Iniciador](https://iniciador.com.br/).
Public [Openi integration documentation](https://developer.openi.com.br/docs/openfinance/tools/postman)
does not establish individual eligibility, cadence or the three-bank product.
Quanto's attempted public site/documentation addresses were inaccessible during
this check; that does not prove the service is closed. These are unqualified
leads, not equivalent alternatives or reasons to purchase a plan.

## Banco MCP: what is established and what is missing

The [published connector list](https://banco.mcp.ai/todos-os-bancos) identifies
Nubank, Inter and Mercado Pago as **PF Open Finance**. Inter and Mercado Pago
also have other connector entries: a later implementation must distinguish the
regulated route. Institution presence does not verify every account subtype,
issued card, installment, bill payment or historical field.

The [personal application guide](https://banco.mcp.ai/guias/construir-gestor-financeiro-pessoal-no-lovable)
explicitly describes consuming one's own connected accounts through a backend
REST client and retaining an application-side copy. This can be investigated
without coupling banking retrieval to an AI model or replacing Django/SQLite.
Its suggested Supabase architecture and matching heuristics are examples, not
Tuxedo requirements. Preserve the initial study's reconciliation rules instead.

The [public Postman collection](https://mcp.ai/openfinance/postman.json)
documents a force-sync operation and account, transaction and bill queries.
It also includes category modification. A future adapter needs an explicit
query allowlist: marketing about not moving money is not a guarantee that every
exposed operation is read-only. Connection refresh/revocation need deliberate
separate permissions; none belongs to an unrestricted AI tool catalogue.

The [webhook guide](https://banco.mcp.ai/guias/webhook-quando-comprar-algo)
requires a public HTTPS receiver and refuses localhost. It describes one delivery
attempt with a 15-second timeout and no automatic retry. Investigate outgoing
REST retrieval and recovery first; do not add a tunnel or public receiver to
the installation implicitly. A webhook notice is not a replacement for fetching
and reconciling authoritative financial evidence.

The [privacy policy](https://banco.mcp.ai/privacidade) describes external token
and operational-metadata processing, with Pluggy as a connection provider.
A local ledger does not make this an offline data path or eliminate the
upstream provider's own retention. A later decision must examine the complete
processor chain and rights to retain/export local evidence after disconnection.

### Questions to resolve before selecting Banco MCP

This is a prepared clarification checklist; it has **not** been sent.

1. Does PF Plus explicitly permit one individual's private Django backend to
   refresh and import their own three regulated PF connections every 6–8 hours?
   What are the actual manual/automatic bank-collection limits, added charges,
   expected delays and indicators distinguishing a cached read from new collection?
2. For each requested bank, which account balances, Pix/transfer counterparts,
   issued-card purchases, installments, open/closed bills and full/partial payment
   records are returned? Supply field/sample documentation and history depth;
   connector names alone are insufficient.
3. Which resources remain daily or less frequent? Are source collection times,
   consent status and partial/stale-result indicators available? Confirm whether
   scheduling is available on this personal plan, rather than only force-sync.
4. Can a local outbound client recover without a public webhook, including
   missed notices, pagination, older restatements, changed IDs and pending-to-posted
   transitions? Which scoped credential avoids granting unrelated workspace tools?
5. What data is retained by DL WEB and Pluggy, where and for how long? What happens
   separately to provider credentials/data and the owner's local evidence when
   consent is revoked, a plan is cancelled or an export is requested?

Public API documentation establishes available shapes, not permission to run a
production trial or a complete freshness/retention commitment. No plan or recurring
cost has been approved. Recheck checkout terms before any later contracting decision.

## Personal MCP alternatives are separate products

Belvo's [Panorama privacy policy](https://panorama.belvo.com/privacy-policy/)
describes a consumer service with selected MCP clients, paginated financial data
and recurring refresh, without a numeric collection interval. It stores service
data on AWS in the United States. Permission for local scheduled ingestion and
retention is not established merely by accepting MCP clients. The current
[commercial OFDA list](https://developers.belvo.com/products/aggregation_brazil/aggregation-brazil-institutions)
lists Nubank and Mercado Pago; Inter was not located in that table. This does not
prove exclusion from Panorama, but neither product can inherit the other's coverage.

The original study's Belvo finding concerned its **commercial API offer**; it
must not be read as denying the separate personal MCP service found here.
An external MCP connection is also not inherited by Tuxedo from ChatGPT, Codex
or a plugin installation. A later backend adapter would require its own supported
authentication, minimal-data handling and approved context boundary.

## Cadence: preserve the requirement and measure the right event

Keep these distinct: when the bank exposes a record, when a provider collects
that resource, when Tuxedo retrieves it, and the date of the financial event.
HTTP rate limits, unlimited questions, cache reads and an accepted force-sync
request do not prove new bank data or a maximum end-to-end age.

| Resource evidence | Consequence |
|---|---|
| [Klavi limits/delay table](https://docs.klavi.ai/connect/rate-limits-and-throughput) labels account/card transactions with a 3-hour maximum delay, and invoices with 24 hours. | This documents per-resource expectations beside operational quotas, not personal eligibility or an independently verified SLA for the three banks. |
| [Polp schedule](https://www.polp.com.br/docs/celcoin/sync-frequencies) describes approximate effective synchronization: account/card transactions eight times daily, but bills and their transactions once daily. | Intraday transaction collection does not make the bill resource intraday; contracting is separately restricted to companies. |
| [Pluggy operational guide](https://docs.pluggy.ai/en/docs/open-finance/rate-limits) separates recent balances/transactions from daily bills and less frequent historical/detail collection. | The provider's general item-refresh interval cannot be applied indiscriminately to every resource. |

Daily bill collection is a known conflict if 6–8 hours is required for **every**
resource. The subsequent owner decision below accepts a daily exception only
for the bill pilot. Keep broader proposals explicit; do not manufacture a recently
refreshed bill from recent card transactions or label a cache-read timestamp as
collection time.

## Daily card-bill pilot — subsequent owner decision

After reviewing the intraday options, the owner proposed focusing on credit-card
bills and explicitly accepted **24-hour updates for this pilot**. Prioritize the
free personal Meu Pluggy path for capability verification. This changes the pilot's
resource scope and cadence; it does not confirm provider behavior, authorize bank
consent, enable imports or accept a paid plan.

| Priority bank | Fresh public evidence | Remaining verification |
|---|---|---|
| Inter PF | The [September Pluggy release](https://docs.pluggy.ai/pt/changelog) explicitly documents regulated Inter PF connector 823 delivering bills when the bank publishes them at closing. | Strongest proposed starting point; verify the bill resource through the free personal proxy and the specific card consent. |
| Nubank | The [regulated coverage matrix](https://docs.pluggy.ai/en/docs/open-finance/institutions-coverage) includes cards, and the September release describes PF card transactions around closing. | Confirm complete bill metadata and associated transactions through the personal route; do not equate transaction access with every bill field. |
| Mercado Pago | The same regulated matrix includes cards; the September release documents future installment behavior. | Confirm PF bill coverage separately. The matrix combines PF/PJ products and does not establish the issued card's full personal coverage. |

The [bill product guide](https://docs.pluggy.ai/en/docs/products/credit-card-bills)
documents structured totals, due dates, charges and payments for supported regulated
credit-card connections. It does not promise a bank-issued PDF. The
[bill-list endpoint](https://v2.docs.pluggy.ai/pt/reference/bill/bills-list)
retrieves collected bills for a credit-card account; individual purchases require
the associated transaction evidence. Open-card activity can lack a confirmed
bill association, so do not fabricate its final total or future installments.

The [personal guide](https://docs.pluggy.ai/en/docs/guides/meu-pluggy-personal-use)
establishes free access and daily refresh, but does not explicitly guarantee the
bill endpoint for every proxy connection. This is a capability to verify, not a
reason to claim either certain availability or impossibility. General regulated
coverage is not proof that a particular PF account's permission and payload are complete.

Recommended first acceptance slice: one closed Inter card bill already published
by the bank, its available purchases/installments, total, due date, charges and
reported payments. Keep the first result read-only and compare it with the bank's
statement before proposing any reconciliation. Do not create a duplicate purchase
or count the bill payment as another expense. Expand to Nubank and Mercado Pago
only after verifying each connection's resources; no bank has been connected here.

Prepare this slice with synthetic data first. A later owner-authorized real read
must identify missing fields and collection time, handle empty/stale/partial
responses without zeroing records, and preserve existing manual transactions and
category splits. Daily provider collection does not mean a local application
updates while it is closed. No publication, public webhook or always-on service
is implicit in the accepted pilot frequency.

## Direct-bank APIs do not replace the missing aggregation contract

| Institution | Official evidence | Scope consequence |
|---|---|---|
| Banco Inter | [API help](https://ajuda.inter.co/conta-digital-pessoa-juridica/o-que-e-uma-api/) explicitly restricts direct APIs to PJ, excluding PF/MEI. | Not a direct route for the current PF account. |
| Nubank | [Open Finance guide](https://nubank.com.br/nu/open-finance-nubank) describes regulated institution-to-institution consent. No public personal developer API contract was found. | Do not substitute private app endpoints, bank credentials or reverse-engineered clients. |
| Mercado Pago | [Developer terms](https://www.mercadopago.com.br/developers/pt/docs/resources/legal/terms-and-conditions) admit individuals; [Account money reports](https://www.mercadopago.com.br/developers/pt/docs/reports/account-money/introduction) and [API generation](https://www.mercadopago.com.br/developers/pt/docs/reports/account-money/api) document approved balance movements. | Potential partial source, not proof of complete own-issued-card purchases/bills, the three-bank scope or a 6–8-hour commitment. Payment-method fields do not establish issued-card coverage. |

## Next implementation boundary

First obtain the missing public or explicitly authorized provider clarification.
If a candidate passes, prepare a disposable synthetic reconciliation proof before
requesting real-bank consent. Reuse the initial study's cases for purchases versus
bill settlement, own transfers, existing manual records, split categories,
installments, refunds, missing data and changed identifiers. Add per-resource
staleness, failed syncs, repeated reads, missed notices and older restatements.

Keep banking data collection independent of model inference. Provider text and
category guesses are untrusted evidence; reuse Tuxedo's canonical calculations
and explicit reconciliation decisions. Store credentials only on the server,
validate ownership and keep external waits outside SQLite transactions.

No new scheduler or always-on service is approved. While the local process is
offline it cannot update its database every 6–8 hours. A future design must make
provider collection versus local retrieval explicit, show the last successful
resource collection and recover safely on use. Existing data must never be
zeroed or erased because collection is late, partial, revoked or unavailable.

## Validation and limits

This increment changes research documentation only. Official public product,
developer, pricing and policy pages were inspected without logging in or calling
financial endpoints. No accounts, credentials, model calls, sales messages,
service purchase, dependency, schema or runtime configuration were involved.
No financial records were accessed or changed. No commit or publication was made.

`uv run python scripts/check_docs.py` passed with 78 documents, 686 local
references and no unresolved targets; `git diff --check` also passed.
Application/browser suites were not rerun for this documentation-only study;
no earlier run is represented as new evidence of provider behavior. Private PF
samples, production cadence, local callbacks and end-to-end reconciliation remain
unverified until separately authorized and actually exercised.
