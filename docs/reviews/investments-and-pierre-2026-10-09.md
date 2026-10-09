# Investments review and Pierre Finance comparison

Reviewed on 2026-10-09 against the current Tuxedo Finance checkout. This is a
product and implementation review, not an investment recommendation. Competitor
capabilities below distinguish published claims from individual user accounts;
no Pierre account was created and its authenticated application was not tested.

## Investment findings and changes

| Area | Finding | Result |
|---|---|---|
| Current portfolio FX | The view combined current conversion failures with failures from a trailing historical chart window. A recent USD rate could be available while an older opening-position rate was absent. | Current positions and historical charts now have separate read paths and warnings. The current total no longer inherits unrelated historical gaps. |
| Missing-rate recovery | The warning identified a currency but gave neither the required date nor a useful recovery path. | Charts disclose each affected opening/operation, required pair/date, and exact rate-registration or operation-editor link. Rate shortcuts leave the price empty. |
| Historical evidence | An operation captured against an earlier reporting currency was rejected even when its native currency matched the newly selected reporting currency. | Native values require no FX. Other historical target mismatches still preserve the saved evidence and explain how to restore its reporting currency. |
| Previously missing evidence | Adding a dated rate alone did not repair an explicitly unknown snapshot; a descriptive edit correctly preserved it. | An unchecked, optional editor choice captures only missing evidence using a valid dated rate. Captured evidence cannot be replaced through that choice. |
| Current valuation presentation | The total did not expose its conversion date or applied rate, and a partial total resembled a complete one. | Recorded native subtotals, conversion date, a rate disclosure with effective dates, and an explicit partial-total label. Foreign monetary positions show their base value too. Zero balances need no rate. |
| Position navigation | Reviewing one position required manually selecting its product and asset in Operations. | Position names open history scoped to that product/asset/purpose. Product actions preselect only an explicitly requested owned product in a new operation; asset/type choices remain deliberate. |
| Operation filters | Documentation promised date, currency and class filters, but the screen supported only purpose, product, bank, asset, kind and search. | Add inclusive dates, native currency and asset class. Invalid criteria retain errors and show no results instead of silently broadening history. |
| Asset lifecycle | Assets with opening holdings or recorded operations were protected from deletion but had no reversible way to leave the active catalog. | Delete unused assets; archive and restore assets without changing holdings, ledgers or reporting totals. Current Portfolio and Remunerated cash lists hide archived positions. New operations exclude archived assets while historical editors retain their current asset. |
| Setup and entry | Shared choices, conditional amount/units, funding, yield previews and protected opening positions already exist. | Retain these contracts; exercise existing setup/operation/rate browser suites alongside the new flows. |
| Banking and planning | Deposits/withdrawals own bank/points entries; internal yield stays in the position. Monetary cash pots contribute separately to planning. | Retain the existing ledgers and classifications. No personal record or rate was inserted by this review. |

The specific USD warning was consistent with a recent rate and an opening
position requiring an earlier chart-window date. A current rate is suitable for
the explicitly dated current conversion; it is not evidence for an earlier
historical conversion. Register a real historical rate if that historical view
is needed, or choose a chart window covered by the available evidence.

## Investment limitations requiring a separate domain change

1. **Unit positions need a defined valuation/cost-basis policy.** The current
   `get_portfolio_groups` and historical curves use signed operation values. A
   purchase of one unit at 100 followed by its sale at 150 has zero units but a
   net recorded value of -50. That is an operation-flow result, not the value or
   acquisition cost of the remaining holding. This review does not silently
   rewrite that accounting policy. Before treating unit totals as portfolio
   wealth, define remaining cost basis, realized results and valuation separately,
   and reconcile the same values across portfolio, dashboard and compositions.
2. **Market valuation and real performance are absent.** There are no persisted
   market-price observations, unrealized gain/loss, cash-flow-adjusted return,
   benchmark comparison or attribution separating FX effects. The current
   simulator is hypothetical; manual internal yield is not a return calculation.
3. **Liquidity and targets are coarse.** Investment/monthly-cash purposes exist,
   but maturities, redemption terms, actual goal balances and target allocations
   are not modeled.
   Opening positions also have no effective date: historical windows assume
   that they were already held at the beginning of the window. A dated opening
   baseline is needed before inferring when a newly entered holding actually
   existed; a recent registration must not be mistaken for acquisition evidence.
4. **Data intake remains manual.** Investment history has no statement import,
   reconciliation queue or financial synchronization. Transaction CSV export
   and category import do not provide investment import or an integration API.

Recommended order: define and correct unit valuation first; then add manual
valuation observations with dates/sources and real performance; then consider
investment import/reconciliation and goal progress. External quotes, banking
connectors and agent access are larger opt-in extensions, not prerequisites for
fixing the current FX warning. See the current
[approved scope](../product-requirements.md#out-of-scope).

## Pierre: useful strengths and actual Tuxedo gaps

| Opportunity | Evidence from Pierre | Tuxedo today | Recommended adaptation |
|---|---|---|---|
| Less manual input | Pierre advertises consolidated account, card and investment connections. A user specifically appreciated bank import, categorization and the yearly summary. [App Store](https://apps.apple.com/br/app/pierre-ia-financeira-pessoal/id6749781755), [Reddit account](https://www.reddit.com/r/ConversaFinanceira/comments/1vfflxb/app_para_controle_financeiro/) | Manual financial entry; exports and category import. No transaction/investment ingestion. | Begin with local CSV/OFX staging, duplicate detection, explicit review and matching existing settlements. Optional bank sync can follow without becoming mandatory. |
| Useful signals rather than more charts | Published alerts cover unusual spending, duplicate charges, forgotten subscriptions and approaching bills. [Official help](https://lp.pierre.finance/ajuda) | Existing forecasts and card/invoice information cover part of the upcoming-payment need. No configurable anomaly/duplicate/subscription analysis. | Add a local review queue with transparent rules, evidence links and dismiss/acknowledge controls. Reuse existing forecast data instead of duplicating it. |
| Natural-language access to recorded information | Pierre describes contextual conversations across accounts and investments. A user praises spending/economy insights after adjusting imported data. [App Store](https://apps.apple.com/br/app/pierre-ia-financeira-pessoal/id6749781755), [Reddit discussion](https://www.reddit.com/r/investimentos/comments/1v57ci4/existe_algum_app_que_una_investimentos_gest%C3%A3o/) | Reports and composition source links already explain numbers; there is no conversational querying. | Start with clear preset questions backed by local queries and source links. An optional assistant should preserve dates, ownership and calculation provenance. |
| Interoperability | Pierre's help advertises API/MCP integration. A user reports consuming Pierre's API in their own financial site. [Official help](https://lp.pierre.finance/ajuda), [User account](https://www.reddit.com/r/investimentos/comments/1v57ci4/existe_algum_app_que_una_investimentos_gest%C3%A3o/) | No public application API/MCP; local SQLite is owner-controlled. | First standardize import/export formats. A read-only, authenticated local integration can be considered later, separately from mutation tools. |
| Access from familiar channels | The help center advertises app, web and WhatsApp access. [Official help](https://lp.pierre.finance/ajuda) | Responsive browser application and desktop/self-hosted operation. No conversational messaging channel. | Prioritize mobile usability and convenient local entry first. A messaging service adds external infrastructure/data handling and should stay optional. |

These are proposed directions, not newly approved or implemented features.
The existing product scope explicitly excludes bank synchronization, statement
imports, market feeds and agent integration.

## What the user accounts change about the comparison

- The user who liked import/categorization also could not register future
  installment payments at the time of their post. Tuxedo already supports
  installments, recurring expenses, forecasts and monthly planning. This is a
  strength to retain, not a feature gap to copy. [Reddit](https://www.reddit.com/r/ConversaFinanceira/comments/1vfflxb/app_para_controle_financeiro/)
- App Store feedback asks for planned income/expenses, reports delayed Open
  Finance synchronization, and requests previewing the interface before giving
  sensitive signup data. Those are dated individual accounts, not proof that
  every current user has those problems. Preserve Tuxedo's native planning,
  static preview and signup without CPF or mandatory bank authorization.
  [App Store feedback](https://apps.apple.com/br/app/pierre-ia-financeira-pessoal/id6749781755)
- One discussion includes both favorable Pierre experiences and users preferring
  their own tools. An API user values automatic intake while retaining their own
  interface. The useful lesson is reducing repetitive work while keeping review
  and control. [Reddit discussion](https://www.reddit.com/r/investimentos/comments/1v57ci4/existe_algum_app_que_una_investimentos_gest%C3%A3o/)

The official landing page and help page disagree on some plan limits and prices;
this comparison deliberately does not rank subscriptions or repeat promotional
yields. The full complaint listing could not be opened reliably, so search
snippets are not used as evidence of defect prevalence. User posts and store
reviews are self-selected and can describe older versions. Promotional privacy,
security and regulatory claims were not independently audited.

## Validation

The repository's disposable browser runner and temporary-data Django checks are
used for this change; never target the installation's runtime database. The
focused regression coverage includes current versus historical FX, direct and
inverse rates, empty rates, zero balances, preserved snapshots, explicit missing
capture, native reporting currency, ownership, dated shortcuts, invalid filter
recovery, protected deletion, archived selections, current position visibility
with retained totals/FX/planning, and preserved positions/ledgers,
keyboard and native/no-JavaScript flows in both themes. Record identifiers above
999 remain unlocalized in archive actions and historical yield previews.

Latest validation completed: 372 Django tests passed with 94% combined
line/branch coverage. All three asset-lifecycle browser tests were rerun after
the archived-position visibility correction, covering both themes, mobile
Portuguese, retained totals/history, restoration and native forms. The broader
investment review previously passed 35 applicable browser tests, including real
keyboard events and nonzero-scroll invalid filter recovery.
Django system/migration checks, executable-correctness lint and `git diff --check`
passed. Compiled CSS and Brazilian Portuguese translations were rebuilt.
