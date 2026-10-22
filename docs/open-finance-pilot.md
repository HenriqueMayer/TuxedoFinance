# Meu Pluggy Inter card-bill pilot

**Current delivery:** An operator-only, read-only Django management command.
It is not an application screen, scheduled worker, importer or financial action.
It does not connect bank accounts automatically or reopen the
[paused statement workflow](apps/ingestion.md#interface-review-gate).

The command targets free personal Meu Pluggy access for Inter credit-card bills
with daily updates. The [provider research](open-finance-research.md) describes
coverage, cadence, consent and reconciliation limits. Its presence does not
establish complete proxy bill coverage or enable a bank connection.

## Offline preparation

From the repository root, using the normal local environment:

```bash
uv run python manage.py pluggy_invoice_pilot --demo --include-transactions
```

This explicitly labelled demo uses synthetic data and makes no network requests.
It creates a private JSON observation under ignored `.local/open-finance-pilot/`.
It performs no database queries or writes and needs no new migration, dependency,
environment variable, API key, bank authorization or assistant connection.

Plain invocation requires choosing `--demo` or `--live`; it never connects by
default. Use `--help` to inspect all options. This technical operator command uses
English diagnostics; no product UI or frontend interaction changes.

## Before authorizing real bank data

Open Finance is a consent-based data-sharing framework, not direct database
access to the bank. The [Central Bank's consumer guidance](https://www.bcb.gov.br/meubc/faqs/s/open-finance)
separates data sharing from payment services and explains consent, bank-side
authentication and revocation. [Inter's own guidance](https://ajuda.inter.co/open-finance/como-compartilhar-dados-pelo-open-finance)
says that sharing starts at the receiving institution and confirmation happens
in the Inter app. Data-only consent does not authorize a payment.

**This path is not entirely local:** Inter shares authorized data with the
receiving participant; Meu Pluggy processes it remotely; Tuxedo then reads a
limited observation into a local private file. Tuxedo's narrow API requests do
not reduce the broader permissions granted to the provider. Inspect the actual
recipient, products, purpose and duration in the bank's consent summary before
confirming. If it includes more than the intended card-data pilot, review that
scope first rather than assuming that only bills are exposed.

Use only the **regulated Inter PF Open Finance** connection. The provider's
[security explanation](https://www.pluggy.ai/blog/seguranca-open-finance-api)
distinguishes regulated connectors (authentication at the bank) from direct
connectors (provider-held encrypted credentials). Its generic landing-page FAQ
and [privacy policy](https://www.pluggy.ai/legal) also discuss bank passwords;
those pages are not proof that a particular connection uses the regulated path.
Never enter a bank password in Tuxedo or chat. Stop if the proposed connector
collects it outside Inter's official environment.

Pluggy appears in the [official Open Finance participant search](https://openfinancebrasil.org.br/quem-participa/?marca=pluggy).
Its legal page identifies Pluggy Brasil IP LTDA, CNPJ 37.943.755/0001-30, and
claims authorization as an ITP. The matching entity and CNPJ base 37943755 also
appear in the [BCB institution list](https://www.bcb.gov.br/fis/tarifas/htms/bancossegmento12.asp?frame=1&idpai=).
A listing or a provider security claim is not an independent audit, a zero-risk
guarantee, or verification of a consent screen that has not yet been inspected.
Confirm the actual receiving institution instead of accepting a similarly named
app.

The provider policy permits service providers and processing outside Brazil.
Revoking consent stops further authorized bank sharing; it is not the same as
erasing existing copies. The general policy describes an approximately 15-day
deletion process with retention exceptions. Confirm deletion timing for personal
backups with the provider. Request deletion through the provider as needed, and
separately remove local observations/backups. The pilot
does not transmit those observations to an AI model.

## Personal setup

Follow the [official personal guide](https://docs.pluggy.ai/en/docs/guides/meu-pluggy-personal-use).
Account consent and code authentication are separate steps:

1. Open [Meu Pluggy](https://meu.pluggy.ai/) yourself. Sign in or create a free
   personal account, select **Inter PF through regulated Open Finance**, and
   authorize the card data through Inter's official channel. No payment or Pix
   initiation scope is needed. Stop if the flow requests a paid commercial plan
   or offers only a nonregulated bank-credential connector.
2. In the Pluggy Dashboard application demo, connect the **MeuPluggy** connector,
   not the Inter connector and not Sandbox. Choose the item corresponding to the
   Inter authorization. The personal path does not require commercial due diligence.
3. Keep that **proxy item ID**, plus the application's **Client ID / Client Secret**,
   locally. Do not paste them into chat, issue descriptions, shell arguments or
   tracked configuration. The item ID is an identifier, not a bank password;
   credentials must be entered through hidden prompts below.
4. Confirm that the source item really is your Inter PF regulated connection.
   The proxy identifies itself as MeuPluggy connector 200, not Inter connector 823.
   Its documented metadata does not prove the original bank; the command records
   your attestation, not provider-verified Inter provenance.

No step asks Tuxedo to receive the bank password, an MFA code or a callback token.
The operator completes those steps at the official bank/provider interface.
Connecting elsewhere in the Dashboard may select a different commercial route;
do not enable billing to work around an error in the personal path.

## First real read

After completing personal setup, run in your own interactive terminal:

```bash
uv run python manage.py pluggy_invoice_pilot --live --confirm-inter
```

The command asks for the known proxy item ID, Client ID and Client Secret without
echoing them. Secrets are used for that invocation only, never saved to `.env`,
the database, report, assistant vault or browser storage. It refuses piped-input
credential fallback. Do not add a credential option or pipe a secret into it.

It validates the personal proxy, item status and authorization expiry before
requesting credit-card accounts. One available card is used; multiple cards
require explicitly selecting the intended account with `--card-id` from the
Dashboard. It chooses the latest bill whose supplied closing date has passed,
or the explicitly supplied `--bill-id` within the selected card. An absent closing
date is not guessed from a balance or due date. No confirmed closed bill means
the probe stops, preserving any earlier observation.

Optional card/bill identifiers are noncredential UUIDs, but remain private metadata.
Use them only on your own computer. The command does not list all personal items:
that endpoint is unavailable for Meu Pluggy accounts. Reauthorization can change
the proxy item ID, so verify it again rather than reusing an unrelated connection.

To also inspect associated purchases/instalments:

```bash
uv run python manage.py pluggy_invoice_pilot --live --confirm-inter --include-transactions
```

The optional query reads a bounded 90-day window for the selected card, then
retains only transactions explicitly linked to the selected bill. It does not
retain other bills' descriptions or assign unlinked purchases by date or merchant.
`--lookback-days` can explicitly extend that window up to 366 days. A bounded
window does not prove complete installment history; compare with the bank's bill.
No entire-client ledger or unrelated bank-account balance is fetched.

## Daily behavior and private evidence

Meu Pluggy refreshes the original connection every 24 hours; the proxy cannot
request manual bank synchronization. This command only reads collected data.
For the same requested item/card/bill/options it reuses a local observation for
less than 24 hours, without a new credential prompt, HTTP request or timestamp
rewrite. A changed selection/window can require another read of already-collected
data. Automatic card/latest-bill selection never reuses a prior explicit card/bill
request, or vice versa. Older incomplete observations are not reused as valid
bills. There is no force-sync, automatic retry, cron, daemon or public webhook.

Run manually/on use to retrieve an observation after that interval. Closing
Tuxedo does not schedule local collection. A recent local read is not proof of
recent bank data, and cached evidence does not revalidate a subsequently revoked
remote consent. The report separates retrieval time, proxy update time and the
unknown underlying bank-resource collection time. Authorization expiry is checked
before reuse; failed/empty/partial collection never zeroes or deletes records.

The terminal prints only mode, counts, warnings and the private report path.
The JSON includes the selected bill's reported native total/currency, dates,
available charges/payment observations and optional linked transaction evidence.
Missing values stay null. It never derives `PAID`, creates a payment, converts
currency or treats an account's used limit as its bill total. The provider may
report a previous bill's payment in the following cycle, so reported payments
are not automatically assigned to a local invoice. This is structured data,
not a bank-issued PDF or evidence of complete reconciliation.

The default directory is `0700`, files `0600`, with hashed filenames and a lock
per mode/item. Existing unsafe ownership/permissions, symlinks and hardlinks
are refused instead of altered. Reports are atomically replaced only after a
successful bounded read; a failure retains prior evidence. Synthetic and live
keys are separate. No report is served through Django or exposed to another
application user or the assistant. File access is restricted to the local OS
operator; it is not a multiuser web authorization mechanism.

Artifacts remain until the operator removes the report/private directory. They
contain private financial observations, not credentials, and are not encrypted at
rest by the pilot. Include them only in deliberately protected backups; deletion
does not erase earlier backups. `--output-dir` can select another private local
directory without moving or changing installation data. Storage currently requires
POSIX permissions and `flock` (Linux/macOS/WSL); unsupported systems fail closed.

## Failure and recovery

Errors use stable codes and never echo provider bodies, credentials or URLs with
secrets. The command accepts only fixed HTTPS auth/item/account/bill/transaction
paths, rejects redirects and environment HTTP proxies, and bounds response size,
page/record/request counts and wait time. Authentication is the only POST; it
does not authorize payments or financial writes. External waits occur outside
SQLite transactions, and the command makes no application database queries.

| Code / state | Operator action |
|---|---|
| `inter_attestation_required` | Verify the original Inter PF regulated connection in the Dashboard before explicitly adding `--confirm-inter`. |
| `not_personal_proxy` | Choose MeuPluggy in the Dashboard; do not bypass this by switching to a direct bank connector or paying. |
| `authorization_expired`, `authorization_expiry_unknown`, `item_not_ready` | Review the official consent/item status. A still-UPDATED item with empty data can have expired authorization. Do not retry repeatedly or assume a zero balance. |
| `multiple_cards_require_card_id`, `foreign_account` | Verify the account UUID belongs to this personal proxy item and identifies the intended card. |
| `closed_bill_unavailable`, `card_unavailable_or_not_authorized` | Inspect card/bill permissions and publication at the bank. Coverage is still unverified for this connection; no record is manufactured. |
| `unauthorized`, `forbidden`, `rate_limited`, `provider_unavailable` | Check personal-route setup, credentials and provider status. There is no paid fallback or automatic repeated request. |
| `request_limit`, `record_limit`, `page_limit`, `response_limit`, `time_limit`, `timeout` | The result is not accepted as a complete observation. Review the bounded collection contract before changing limits. |
| `pilot_busy`, storage/path/permission error | Wait for an existing read or select a safe private directory. Do not weaken permissions or overwrite unrelated data. |

The [ingestion guide](apps/ingestion.md) owns future source-preserving import
decisions. This pilot proves neither complete bank coverage nor authorization
to create transactions, settle invoices, categorize, modify balances or pass
financial evidence to a model. Those remain separate deliveries.
