# Changelog

Changes that the owner of an installation can notice. Versions follow
[Semantic Versioning](https://semver.org/).

## Unreleased

## 2.0.0 — 2026-11-11

2.0 is a new application on the 1.x financial rules. It has a new database
and no upgrade from 1.x.

### Added

- A React client and a JSON API replace the server-rendered pages.
- One month control in Transactions and in the month window: a step to each
  side, and the months of a year behind the name of the month.
- Lists with a search box, a calendar and a file field of the application in
  every form, in place of the controls of the browser. On a phone they open
  as a sheet at the bottom of the screen.
- A field for an amount writes its separators while the owner types.
- A setting for how numbers are written: 1.234,56 or 1,234.56.
- The options of an entry (repeat, installments, note) are in view.
- An analysis of one account, card or investment, opened from its window:
  twelve months of the item and its part of the total of its kind.
- An analysis window, opened from Home: income and expenses, categories, net
  worth and investments over a period of months, against the period before.
- Four destinations: Home, Transactions, Wallet and Plan.
- Debit cards in the Wallet, beside accounts and credit cards.
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
- Plan on one page: a limit of the month and category budgets that hold from
  their month on, and goals that reserve a part of an account or investment
  balance.
- Left to spend counts from the limit of the month when there is one.
- A Goals block on Home.
- Months ahead on Plan: the cash that the records expect, and the balance at
  the end of each month.
- A sheet to try changes on those months, with saved sheets.
- Calculators: net CLT salary and compound growth.
- Accounts in other currencies, exchange rates typed in Settings, and
  transfers between currencies.
- Statement import (OFX and CSV) in Transactions: review each row, confirm
  all at once, undo.
- Points and miles in the Wallet: points earned, used and expired, and a
  redemption for money in an account.
- Month closing: compare each account with the bank, see the result of the
  month and set the next limit. Home asks for it once a month.
- A public page that runs the application with fictional data, in the
  browser, without a server. It replaces the 1.x preview page.
- Categories are exported to a CSV file and imported from one.
- Actions are buttons with icons, a card lifts under the pointer, and the
  page of a destination changes with a short transition.

### Removed

- The assistant.
- The automatic alerts (possible duplicates, subscription increases, cash
  shortage, goals behind). A budget and a goal show their own state.
- Pages that work without JavaScript.
- The Django admin.

## 1.x

The versions before 2.0 were a server-rendered Django application. Their
notes are in the changelog of the tag
[`v1.0.2`](https://github.com/HenriqueMayer/TuxedoFinance/blob/v1.0.2/CHANGELOG.md).
