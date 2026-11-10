# Changelog

Changes that the owner of an installation can notice. Versions follow
[Semantic Versioning](https://semver.org/).

## Unreleased — 2.0.0

2.0 is a new application on the 1.x financial rules. It has a new database
and no upgrade from 1.x.

### Added

- A React client and a JSON API replace the server-rendered pages.
- Four destinations: Home, Transactions, Wallet and Plan.
- Every object opens in a window above the current page. A window has an
  address, and the page behind keeps its position and filters.
- Add entry on every screen, with the key N. A known description fills the
  category and the account or card.
- Home with blocks that the owner shows, hides and orders: Left to spend,
  Where the money went, Due soon, Net worth.
- A line on Home that says whether the records are up to date.
- A monthly schedule for a repeating entry: confirm, skip or restore a month,
  and change the amount from a month.
- One settlement setting for each credit card: the owner confirms each
  invoice payment, or the invoice is paid from the account on its due date.

- Investments in the Wallet: a balance or units with a price, deposits and
  withdrawals with an account, and one field for the value of today.
- Net worth: accounts and investments less the card debt, with the last
  twelve month ends.

### Not built yet

Plan (limit, budgets, goals, sheet), loyalty points, accounts in other
currencies, statement import and the public site.

### Removed

- The assistant.
- Pages that work without JavaScript.
- The Django admin.

## 1.x

Versions 0.3.0 to 1.0.0 were a server-rendered Django application. Their
notes are in the changelog of the tag
[`v1.0.0`](https://github.com/HenriqueMayer/TuxedoFinance/blob/v1.0.0/CHANGELOG.md).
