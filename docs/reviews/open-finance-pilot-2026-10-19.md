# Meu Pluggy Inter bill pilot — 2026-10-19

## Scope

The owner approved the free personal Meu Pluggy pilot, initially Inter credit-card
bills with daily updates, preserving existing data and without publication.
The [owning guide](../open-finance-pilot.md) describes the available command and
recovery, separate from the [research](open-finance-intraday-study-2026-10-19.md).

Implemented a standalone operator command inside the existing ingestion app,
without model/schema, dependency, setting, URL, UI or feature-gate changes.
The first capability is private read-only evidence, not an import/settlement.
Credentials enter through hidden interactive prompts and remain in memory only.
No installation `.env`, assistant vault, database or existing local data was read
or changed during development/verification.

The fixed-origin provider adapter supports only auth and scoped item, credit-card,
bill and optional transaction reads. It refuses redirects, foreign identifiers,
unsafe pagination and unbounded responses/waits. A separate private artifact store
uses owner-only POSIX permissions, locks and atomic replacement. Demo/live identity
keys do not overlap. Daily cache reuse neither contacts the provider nor rewrites
the observation. Failures retain prior evidence.

The documented personal proxy has connector 200 rather than original Inter 823;
the source bank is explicitly operator-attested. Bill records retain native
amounts/dates, missing fields and reported payments without deriving PAID. Only
exact supplied bill links select transaction evidence; unknown links remain
unassigned. A bounded transaction window does not establish completeness.

## Validation

Validation used isolated settings, disposable synthetic records and temporary
private directories; `.env` was disabled and the data/vault paths were temporary.

- **51 focused tests passed:** bounded/allowlisted transport, pagination, safe
  failures, monetary precision, report provenance, cache scoping and private
  storage, including foreign records and malformed responses.
- A seeded domain snapshot remained identical and the command executed with
  **zero database queries**. `SimpleTestCase` also forbids database access in
  the command/provider/report cases. No real credentials or bank requests were used.
- The CLI synthetic demonstration produced the labelled closed bill and one
  explicitly linked synthetic purchase. Its directory/files were verified as
  `0700`/`0600`, and Git ignores the output. Demo/live keys remain separate.
- Version consistency and Django system checks passed; no migration changes.
  **44 repository-tool tests passed**. Executable-correctness Ruff passed for the
  repository. The documentation checker resolved **702 references in 80 documents**;
  `git diff --check` passed.
- After the final cache fixes, a fresh full Django run with stable source files
  passed **1,021 tests in 166.673 seconds**. The repository-configured branch
  coverage report passed its 70% gate at **95% overall** (including test modules
  in the configured source set). The new provider/report/store/command runtime
  subset is **91%**, excluding its tests. This supersedes an intermediate run
  invalidated by mixed old/new imports while the command signature was being
  edited.

Independent read-only review found no ledger-write or credential-output path.
It reproduced two cache correctness gaps, both fixed and covered: incomplete
nested bill/source evidence could be reused, and an automatic latest-bill request
could reuse a prior explicit selection. Cache reuse now validates identities and
closed dates and requires the exact originally requested selection, including
omitted selectors; it does not infer that intent from a resolved card/bill.

## Public security and consent review

After the owner asked for beginner guidance before connecting a bank, the pilot
remained offline while reviewing the Central Bank's consumer guidance, Inter's
official sharing instructions, the Open Finance participant search, and Pluggy's
legal, personal-use and connector-security documentation. The
[owning guide](../open-finance-pilot.md#before-authorizing-real-bank-data) records
the sources and distinguishes bank-side regulated authentication from direct
credential-based connectors, provider cloud processing from local storage, and
revocation from deletion. The provider's generic password copy and broad privacy
policy cannot establish which path an unseen consent screen actually uses.

The public directory displays the Pluggy brand; the BCB institution list also
contains the matching legal entity and CNPJ base 37943755. No live BCB
authorization certificate, internal security audit, penetration test, exact
downstream subprocessor inventory, or end-to-end deletion/backups verification
was obtained.
The real receiving institution and permission groups remain to be checked before
bank consent; a card-only client does not imply a card-only provider consent.

## Remaining live boundary

No real bank authorization, personal account, provider credential, financial HTTP
request, model call, purchase, scheduler, public receiver, commit or publication
was performed. The operator still needs to authorize the Inter card through the
official bank/Meu Pluggy flow and select the personal proxy in the Dashboard.
The prepared live command can then test the selected card's returned bills.

This implementation does not prove free-proxy bill availability, complete
installments, reported payment cycle meaning for an actual card, or an end-to-end
freshness guarantee. Browser tests are not applicable to this command-only slice;
no frontend assets or translations changed. No previous browser evidence is reused
as validation of bank coverage.
