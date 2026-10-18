# `dashboard`

The dashboard composes banking cash, categorized cash flow, card liabilities
and investments. It owns no model and never treats raw transaction amounts as an
account ledger.

Before composing either dashboard or reports, the views call
`sync_user_ledger`. Query helpers are read-only, but the complete request can
write derived movements and invoices. See the
[synchronization boundary](../architecture.md#request-time-synchronization).

## Overview

The main screen presents:

- a live available-cash total and compact native balances by bank account;
- selected-month opening, balance change and closing balance;
- income, expenses, investment deposits and withdrawals for the selected month;
- a top-six categorized-expense breakdown;
- compact open-invoice previews and upcoming due dates;
- a six-month outlook from recurring transactions and scheduled invoice payments.

Reports remains accessible through the workspace's section tabs; the category
summary has no separate Reports shortcut.

Account shortcuts open the exact owned account row, including accounts outside
planning availability. They retain the native fragment and bypass the shell's
generic scroll-to-top behavior. The live **Outstanding invoices** preview includes
scheduled, partially paid and overdue invoices, regardless of the selected
performance month. **All invoices** opens the complete card overview without
narrowing statuses; its scope is deliberately broader than the preview.

The category ledger keeps full labels and separate amount/share values, with
44px selection targets. Outstanding invoices reuse the saved card miniature;
long bank/card names wrap without widening the page. The six-month outlook
retains every numeric column inside a named, keyboard-focusable scrolling region.

For the current month, performance is split at the local current date. One-off
transactions use their recorded date, fixed recurrences keep their configured
day (clamped to the target month's last day), and installments remain known
obligations from their original purchase. Investment and loyalty events use
their own event date. The portion after the cutoff is shown as planned. Past
months are complete; future months are entirely planned. Category totals follow
the same current/past/future rule.

Realized transaction/category amounts and points-purchase costs convert at the
earlier of the month end and the realized cutoff. A future-dated exchange rate
cannot fill an earlier evidence gap. In the current month's full total, already
realized occurrences retain that cutoff and future occurrences use month-end
conversion. Remaining planned activity therefore excludes FX revaluation of
already realized events. Future months retain their month-end valuation.
Composition details use the same cutoff as the mark they explain.

Per-user base currency is implemented through `UserPreference`. Historical
investment operations consume their persisted FX evidence; account balances,
transactions and movements still use explicitly current/read-time conversion.

## Accounting rules

`BankMovement` is authoritative for available cash. PIX and debit movements
appear immediately. Credit purchases appear in expense analysis and invoice
liabilities, but not in account balance. In default automatic mode, the
invoice's single due-date movement reduces cash; that projected settlement is
not external confirmation. Optional manual mode uses only confirmed actual-date
payments for cash. Neither settlement creates another expense. Manual unpaid
amounts appear separately as due-date forecast obligations without becoming
synthetic cash movements.

Own-account transfers are visible in account ledgers but net to zero in
consolidated cash and are excluded from income/expense.

Investment deposits and withdrawals move cash between banking and the portfolio
without becoming income/expense. Yield affects investment value internally; it
does not increase available bank balance.

The dashboard keeps economic performance distinct from cash settlement. Income
and expenses describe activity assigned to the statement month. Projected closing
balances, available cash and the current month's through-today cash change
come from dated account movements plus separate unpaid manual obligations for
the forecast portion. Card purchases therefore stay in their
statement month while actual account cash changes when the invoice is settled.
The live account and open-invoice panels always describe today, even while
another month is selected.

## Reports

The summary has three cards:

- **Balance now:** bank cash through today, even when browsing another chart
  window. Investments are not included in this available bank balance.
- **Projected (month):** the anchor month's inflows minus outflows, using
  `income + recorded withdrawals - expenses - investment deposits`. The card
  identifies that month and does not add an opening balance. Card expenses retain
  their statement-month attribution, consistent with the monthly flow chart.
- **Net change (12 months):** the final bank balance minus the opening bank
  balance for the whole displayed window. Its question-mark disclosure states
  the exact window and explains that it can include historical and projected
  months. The calculation and missing-exchange-rate warning are preserved.

Question-mark help follows the shared [tooltip contract](../frontend.md#question-mark-help):
hover or keyboard focus opens one readable box; pointer exit, outside click and
Escape dismiss it. Touch toggles it, and native details remain the no-JavaScript
fallback. Formulas and explanatory paragraphs are visually separated. The former best-month
summary card is removed. A liquid investment becomes bank cash only through a
recorded withdrawal; merely being redeemable does not create a future inflow.

Reports retain server-rendered SVG/CSS and HTMX-enhanced filters with plain GET
fallbacks. Wide charts retain readable axes in named, keyboard-focusable regions;
phone layouts show a horizontal-scroll hint. Current-month and rolling-year
states occupy the same 44px targets as their links and expose `aria-current`.
Instrument names and selection summaries wrap locally, while SVG label geometry,
period scopes, source amounts and composition interactions remain unchanged.
The approved report set is organized by source of truth:

1. Available cash evolution from account opening balances and movements.
2. Monthly income and expenses from categorized transactions, with investment
   deposits and withdrawal credits shown as separate cash-flow series.
3. Spending by category and settlement instrument.
4. Credit-card invoice evolution, due dates and paid/open status.
5. Currency-aware balances with persisted investment-operation snapshots and
   clearly labeled current/read-time valuations for entities not yet covered.
6. Dated net-worth evolution combining bank cash, investment/cash-pot positions,
   incurred card debt and any confirmed card credit.

The net-worth interface in item 6 is currently paused; its underlying read
model remains available. See the [redesign roadmap](../roadmap.md).

### Coverage of expense breakdowns

Monthly expenses and their cash-flow composition include points purchases and
legacy redemption IOF not already represented by a categorized transaction.
Category budgets, category breakdowns, recurrence breakdowns and account/card
activity currently cover categorized transactions only. A points purchase is
therefore a valid reason for those breakdowns to differ from the monthly total;
it is not another cash debit or an automatically classified budget expense.
The full cash-flow composition identifies it as Bank costs and links to its
owned source. Assigning categories/budgets to these costs is a separate product
decision; do not synthesize another transaction or movement to make totals match.

Charts must label actual versus projected values. Forecasts may include future
recurrences and invoices. Synchronization may store future-effective
projections, but they must not affect today's cash early; manual payment
forecasts never create confirmation records or cash movements.

Ctrl-opened composition rows link to the owned records contributing to that
exact chart scope. A single source opens its existing editor or account context;
multiple sources disclose dated links and their scoped amounts. Recurrences and
installments link once to their original transaction, while generated IOF links
to its source redemption. Opening investment positions link to the asset rather
than inventing an operation. Portfolio valuation compositions instead link each
product/asset position to its scoped operation history and use its dated value,
without summing sale proceeds as remaining holdings. Source amounts reconcile to the existing aggregate,
including fractional FX cents; missing conversions remain explicitly incomplete.
Navigation retains the report period and browser Back/Forward context. See the
[chart interaction contract](../frontend.md#previous-screen-continuity-and-balance-ranges).
From Home and Reports, composition source links also carry the current query and
the owning chart's anchor as a validated local return destination. Existing
editors use it for Save/Cancel; their ownership checks and generated-record locks
remain unchanged.

The instrument and recurrence charts each expose **Last 12 months**, covering
the current calendar month and the previous eleven months. The existing `ALL`
query value remains compatible, but does not mean the entire ledger history.
Their independently selected periods and composition details retain the same
scope.
When an instrument month is empty, **New transaction** remains available on both
full-page and HTMX responses and carries that report period and chart anchor
into the editor's Save/Cancel context.

The twelve-month evolution window contains five months before its anchor and
six after it. Its anchor can move at most five months beyond the current month,
so the displayed window ends eleven months from now. The dashboard's six-month
outlook can start at most six months ahead and shares that same final month.
The ledger synchronizes through today's day twelve months ahead, which does not
cover that last calendar month's late payments. Neither screen therefore shows
that partial month as a complete closing-balance forecast. Forward controls stop
at the boundary; out-of-range GET parameters return to the current window. Past
windows remain available while their opening balance date is representable.

## No-double-counting checks

- Never subtract a credit purchase from available cash before invoice payment.
- Never count an invoice payment as a second expense.
- Never count both sides of an own transfer as income/expense.
- Never classify investment deposit/withdrawal as consumer cash flow.
- Do not silently treat unlike currencies as equal. Historical transfer and
  investment totals use persisted FX snapshots; missing conversion is explicitly
  incomplete elsewhere.

## Dated wealth

**The interface is paused:** old requests to `/dashboard/wealth/` return to
Dashboard through the server review gate. This section describes the retained
read model, not a currently available navigation destination. See the
[redesign roadmap](../roadmap.md).

The retained view reads
`dashboard.wealth.wealth_snapshot(user, as_of, *, conversion=None)` at
month-end cutoffs, capped at today for the current
month. The GET start-month filter covers up to ten years and has a native form
fallback. This is a dated resource history, not an annualized return chart.

Each snapshot combines applicable account openings and movements, replayed
investment positions valued with local quotes or disclosed remaining-cost
fallbacks, and incurred credit-card obligations. A card purchase incurs its
whole unpaid amount when purchased, including installments not yet billed.
Future occurrences of a fixed template are not existing debt; only occurrences
through the cutoff are included. Loyalty point purchases and generated IOF use
their original dated sources without duplicating their invoice charges.
Only the recorded sources modeled here contribute; unrecorded loans, property
or other assets/liabilities are not inferred from cash or statement descriptions.

Confirmed manual payments reduce debt only from their actual date. Automatic
settlements use the amount and effective date of their existing settlement
movement. A payment exceeding incurred debt after a source correction, or a
due-date automatic debit preceding an explicitly overridden future purchase,
appears as card credit. It is added to assets rather than silently discarded or
subtracted as negative debt:

```text
assets = bank cash + investment/cash-pot value + card credit
net worth = assets - positive incurred card debt
```

Cash-pot deposits and withdrawals move value between existing assets; they do
not increase net worth by themselves. Goal reservations earmark those assets
and are not an additional asset or liability. Empty foreign accounts require no
FX for zero balances. Missing conversions from banking, cards or positions are
merged into the snapshot's incomplete metadata; unlike currencies are never
added directly.

Older nonzero openings with unknown dates remain visible but make the history
incomplete. A missing local unit quote shows cost fallback explicitly, so the
result is not a fully observed market valuation. Editing source history, local
quotes or read-time rates can change this reconstructed history; it is not an
immutable external bank statement. Captured investment-operation FX evidence
remains protected.

## Resources versus activity

Planning availability comes from the shared Banking read model: included bank
balances plus monetary cash pots, minus set-aside funds. It remains a current
snapshot regardless of the selected performance month. Missing exchange rates
make the displayed consolidated total explicitly incomplete.

Income and expense performance retain statement-month attribution. Bank closing
balance projections follow effective movement dates, including invoice due dates
in automatic mode, planned manual obligations, and the actual bank cash legs
of investments. Points-funded deposits create no
bank cash outflow. Cash-pot movements are not investment-contribution metrics.
The selected future month is bounded so the six-month outlook stays inside the
existing twelve-month synchronization horizon; the UI disables forward navigation
at that limit.


## Net-worth interface review

The net-worth interface is absent from navigation; its route-level review gate
returns old requests to Dashboard. Its redesign is tracked in documentation. `wealth_snapshot` and financial calculations remain available
to their existing consumers. Dashboard and Reports retain their organization;
paused pending-import calls to action are not shown while review is unavailable.
Per-position cash participation changes planning availability, preserving actual
balances, debt, history and wealth calculations.
