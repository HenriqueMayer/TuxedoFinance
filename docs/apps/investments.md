# `investments`

The investments app remains a separate position ledger. It reuses `banking.Bank`
and `BankAccount` for providers and cash legs, but investment operations do not
become ordinary categorized transactions.

## Domain

```text
Bank
└── InvestmentProduct
    └── InvestmentOperation ── Asset

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
Monetary assets use an investment amount; unit-based assets use quantity and unit
price. There is no `title`.

| Kind | Banking requirement | Position effect |
|---|---|---|
| `DEPOSIT` | Source `BankAccount` required; creates linked debit movement. | Adds acquired quantity/cost basis. |
| `WITHDRAWAL` | Destination `BankAccount` required; creates linked credit movement. | Removes quantity and records proceeds. |
| `YIELD` | No source or destination account. | Internal growth only. |

A deposit source and withdrawal destination are mandatory even when the account
belongs to the same bank as the product. Cross-currency operations retain their
native cash and asset amounts. Retained historical conversion evidence is
planned for ROADMAP Phase 4. The operation and its required movement are posted
atomically.

Yield is internal: it changes the portfolio position/value and appears in
investment performance, but does not create bank income or available cash. Cash
exists only after an explicit withdrawal to a destination account.

## Valuation

Portfolio totals are grouped by bank, product, asset class, asset and currency.
Historical charts value each operation with the rate effective on its date;
current portfolio simulations may use a current rate but must label the
valuation date. Missing rates remain explicit and never cause unlike currencies
to be summed directly.

## Settings and integrity

Investment Settings manages products and assets; bank management links to the
canonical banking screen instead of duplicating it. Referenced banks, products
and assets cannot be deleted. Personal operations remain editable; audit-grade
reversal workflows are out of scope.

All forms and services enforce per-user ownership for bank, account, product and
asset choices. Filters cover bank, product, asset, asset class, currency, kind
and date without changing the unfiltered portfolio totals.

## Charts

The existing server-rendered, responsive chart pattern remains. Charts cover
position/value evolution, monthly deposits/withdrawals/internal yield, asset
class allocation and native/base currency exposure. HTMX is progressive
enhancement; every filter and navigation control retains a normal GET fallback.
