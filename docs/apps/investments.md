# `investments`

The investments app remains a separate position ledger. It reuses `banking.Bank`
and `BankAccount` for providers and cash legs, but investment operations do not
become ordinary categorized transactions.

## Domain

```text
Bank
└── InvestmentProduct
    └── Investment ── Asset

Asset = name + code + asset class + currency + valuation mode
```

`Institution` is removed. A product belongs to one owned `Bank`; a bank may hold
bank accounts, investment products, or both. `Asset.asset_class` and currency
are mandatory and immutable after use because changing either would reinterpret
historical positions.

## Valuation modes

Assets use one immutable valuation mode after their first operation:

| Mode | Use case | Operation value |
|---|---|---|
| `MONETARY` | Savings pots and cash-like balances. | `amount` in the asset currency. Quantity and unit price are not used. |
| `UNITS` | Traded assets such as shares, funds and crypto. | `quantity * unit_price`. |

A monetary asset may have an `opening_balance` and its holding product: money already held before the first recorded operation. It appears in the position balance but does not create a bank movement, income, expense, deposit or withdrawal. It can only be changed before the asset has investment operations. Unit-based assets always have an opening balance of zero.

## Operations

Every operation records product, asset, kind, currency, date and optional notes.
Monetary assets use an operation amount; unit-based assets use quantity and unit
price. There is no `title`.

The create/update form progressively reveals the valuation fields from the
selected asset: monetary assets show an amount labeled for the selected operation, while unit-based
assets show quantity and unit price. Deposit, withdrawal and yield labels also describe acquired, withdrawn or earned
quantities, their unit prices and the actual account debit/credit. Bound forms
render the same labels on the server; client transitions update labels and help
names without changing accounting semantics. The selected operation kind similarly
reveals the applicable funding source or withdrawal destination. JavaScript
only enhances disclosure; without it, all fields remain available and the same
server-side ownership and financial validation remains authoritative.

| Kind | Banking requirement | Position effect |
|---|---|---|
| `DEPOSIT` | Exactly one source account or loyalty program; creates a linked bank movement or points debit. | Adds acquired quantity/cost basis. |
| `WITHDRAWAL` | Destination `BankAccount` required; creates linked credit movement. | Removes quantity and records proceeds. |
| `YIELD` | No source or destination account. | Internal growth only. |

A deposit requires exactly one funding source: a `BankAccount`, or a
`LoyaltyProgram` with a positive points amount. A withdrawal always requires a
destination account. Cross-currency operations retain their native cash and
asset amounts and the applied FX snapshot when conversion is available. Missing
rates preserve native data and mark conversion incomplete. The operation and
its required bank or points ledger entry are posted atomically.

Yield is internal: it changes the product's position/value without creating a
bank movement. Remunerated cash contributes to planning availability while held
in the pot; paying a bill from a bank account still requires an explicit
withdrawal to that account. Long-term investment holdings stay outside planning
availability.

For monetary assets, such as savings pots, a yield can be entered either as the
yield amount or as the new total balance. When the total balance is entered, the
application calculates and stores only the difference from the position that
existed immediately before the operation. The form previews the previous
balance, calculated yield and resulting balance before saving. Operations on the
same date use their registration order; no bank movement is created.

Automatic monthly and annual yield calculations are not implemented. Yield
is entered manually; the total-balance option derives the operation amount
from the supplied balance without introducing automatic accrual.

## Valuation

Portfolio totals are grouped by bank, product, asset class, asset and currency.
Historical charts use captured and reconstructed FX snapshots. Descriptive
edits retain the snapshot; amount, asset, fee, or date edits refresh it.
Changing the reporting currency does not chain a mutable rate onto historical
evidence; snapshots targeting another base are reported as incomplete.
Current portfolio
simulations may use a current rate but must label the valuation date and source.
Missing rates remain explicit and never cause unlike currencies to be summed
directly.

Current portfolio reads are separate from historical charts. A missing opening
rate at the start of a chart window must not mark a currently convertible
portfolio incomplete. Current screens display native currency subtotals, the
conversion date and applied rate/effective date; a partial total is labeled as
such. Zero positions require no FX. Monetary foreign positions also show their
base amount, without replacing the native value.

Chart conversion details identify each opening/operation and the required date.
Rate-registration links preselect the pair/date, never the price. Unknown
operation evidence can be captured explicitly with an unchecked editor choice
after a dated rate exists; it cannot replace captured evidence. Historical
target mismatches explain which reporting currency owns the saved conversion.
Native values need no FX when they already match the selected reporting currency.

## Settings and integrity

Investment Settings manages products and assets; bank management links to the
canonical banking screen instead of duplicating it. Referenced banks, products
and assets cannot be deleted. Personal operations remain editable; audit-grade
reversal workflows are out of scope.

All forms and services enforce per-user ownership for bank, account, product and
asset choices. Filters cover bank, product, asset, asset class, currency, kind
and date without changing the unfiltered portfolio totals.

Operation date filters use the shared preferred-date controls and inclusive
bounds. Invalid criteria retain their errors and return no results rather than
silently widening the history. They remain GET forms with native submission and
HTMX/history support. Currency, class and dates use a native More filters
disclosure; active criteria and invalid submissions keep it open. Filter swaps
preserve scroll and focus instead of returning to the top of the form.
Position names link to history for the exact purpose,
product and asset; product-level New operation links preselect only an owned,
explicitly requested product. Asset and operation type still wait for selection.

For valuation limitations and a dated competitor comparison, see the
[2026-10-09 investment review](../reviews/investments-and-pierre-2026-10-09.md).

## Charts

The dedicated Charts tab at `/investments/charts/` uses the existing responsive
SVG charts and exact selection/composition data. Its Overall, Portfolio and
Remunerated cash filter scopes both the historical position curve and monthly
deposits, withdrawals and internal yields. Overall includes both purposes;
opening positions remain visible even without operations. It does not include
ordinary bank cash or imply market-price valuation.

Changing the scope immediately applies the filter while preserving each chart's
month window, focus and scroll. The Filter button is the no-JavaScript fallback.
HTMX updates only the chart region;
ordinary GETs, browser history, keyboard selection and no-JavaScript filtering
remain available. Missing FX warnings appear inside that same region so filtered
or refreshed charts cannot silently lose their incomplete-conversion warning.

Portfolio and Remunerated cash retain their position tables and contextual links
to the separate Operations page. Operation search/filter/pagination updates only
`#investment-movements`; charts use their own `#investments-charts` region.

## Form keyboard behavior

Record selectors use the shared keyboard-search component. Values and funding wait for the asset and operation type; monetary yields require an explicit input mode. New asset valuation choices begin empty, and opening-position products wait for an opening balance or quantity. Existing operations and invalid POSTs preserve their values and visible errors.

Deposits first ask whether funding comes from an account or a loyalty program.
Only that record selector is revealed; points wait for a selected program and
unit-asset cash amounts wait for an account. Withdrawals put the destination
before its cash amount. Switching source clears incompatible records and amounts.
The presentation choice is inferred from existing operations and native/legacy
submissions; server validation still requires exactly one valid funding source.
Every error-bearing branch remains available after an invalid POST.
Monetary yield input modes precede their value fields, so Tab proceeds from the
chosen mode to the revealed amount or ending balance and its contextual help.

Optional fees live in Advanced options, which opens for existing fees or errors.
For opening unit positions, the unit price waits for a positive quantity and
returns to zero when the quantity is deliberately cleared. Initialization and
browser-history restoration preserve bound values and errors.

Follow the [mandatory shared form contract](../frontend.md#keyboard-and-choice-contract).

## Purpose and cash planning

Products have purpose `INVESTMENT` (the additive migration default) or
`MONTHLY_CASH` (Remunerated cash). Monetary positions in the latter contribute
to planning availability and are shown separately from the investment portfolio.
A monetary asset may occur in different products: purpose belongs to the product,
and the authoritative position is the product/asset pair. A cash product cannot
hold unit-priced assets, including opening positions and historical operations.
Reclassification changes analysis, not the underlying operations or bank ledger.

Deposits and withdrawals between an included account and a cash pot are internal
to combined planning resources. They still change the individual bank balance.
Record actual yield as an ordinary yield operation, using an amount or ending
balance. It changes only the pot until redeemed. Historical investment value is
not a live market valuation; the UI labels this distinction explicitly.

Asset deletion is blocked by any nonzero opening-position component or any
operation history, including a fully withdrawn position. The shared deletion
policy covers instance, QuerySet and Admin deletion and rolls back mixed batches.
Products remain protected by operation and opening-position references.

Asset configuration offers Delete for unused assets and Archive for every active
asset. `is_archived` defaults to false for existing and new assets. Archiving is a
reversible, owner-scoped POST that changes catalog and new-operation availability
and hides the asset's current position rows in Portfolio and Remunerated cash.
Empty product and bank groups are omitted from these lists. Opening positions,
operation history, bank/loyalty ledgers, charts and portfolio/planning totals
continue to include the asset. Valuation happens before display filtering, and
the list explains retained totals when archived positions are hidden. Restoring
an asset shows its positions again. Archived assets appear in a native
disclosure with Restore and retain their unique per-user code. Deletion remains
subject to the same protection, including after archiving.

New operation choices and asset shortcuts exclude archived assets. Model
validation rejects creating an operation with an archived asset or changing an
existing operation to a different archived asset. Editing an existing operation
keeps its own archived asset selectable, with its bound values and errors;
historical filters include all assets. Restore before recording any new deposit,
withdrawal or yield. This rule deliberately keeps archiving distinct from
removing holdings or rewriting history.

The portfolio and Operations pages highlight Configure investments until the
user has a bank, a product and an active asset. Configuration lists the three setup
steps, marks completed prerequisites and links to the next missing registration.
Once ready, New operation becomes the primary action, even before the first
operation. Products are grouped by bank and assets remain a separate editable
catalog. Configuration stays in the investment navigation for later maintenance.

Simulate returns is a gray, non-navigating item in investment sections. Its
floating notice opens on hover, keyboard focus or touch and directs users to
Planning → Yield simulation. The investment submenu has no simulation link;
Planning retains the working destination. The notice uses a text trigger rather
than a question-mark help icon, shares floating positioning/dismissal behavior,
and has a native disclosure fallback for keyboard and touch. Saved scenarios and their hypothetical
yield never post investment or bank movements.
Market quotes, price histories and agent integration remain roadmap work.
