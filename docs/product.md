# Product

Tuxedo Finance is a self-hosted personal finance application for one person
who enters data by hand. It has no bank connection. An entry takes a few
seconds, and Home answers the owner's questions about the month.

## Destinations

The rail (wide screen) and the dock (phone) hold the same four destinations
and the Add action. Settings opens from the rail or from the phone header.

| Destination | Answers | Holds |
|---|---|---|
| Home | How is this month? | Blocks that the owner chooses and orders |
| Transactions | What did I record? | The entries of a month, with search and filters |
| Wallet | What do I have and what do I owe? | Accounts by bank, cards, invoices, transfers, investments |
| Plan | What do I intend? | Not built yet |

## The window

Every object opens the same way: in a window above the current page, from the
element that was pressed. The page behind keeps its position and its filters.
A window has an address, so Back closes it and a link reopens it. See
[`web/DESIGN.md`](../web/DESIGN.md#the-window).

## Entries

- Add is on every screen. The key N opens it.
- A new entry needs an amount, a description, an account or card, and a
  category. The date is today unless changed.
- A description that was used before fills the category and the account or
  card of that earlier entry.
- A credit-card purchase can be paid in installments. Each installment counts
  in the month of its statement.
- An entry can repeat every month, with an optional last month. A repeating
  entry on an account can ask for a confirmation of each month; an unconfirmed
  month does not change the account balance.
- The amount of a repeating entry with past months changes in its monthly
  schedule, from a chosen month. Past months stay as they were.

## Months

A month groups entries by *billed month*: the statement month for a
credit-card purchase, and the month of the date otherwise. Transactions, Home
and invoices use this one rule, so their totals agree.

## Wallet

- A bank is a group of accounts. It appears with its first account and goes
  with its last one.
- An account has an opening balance. Its balance is that amount plus its
  movements up to today.
- A credit card belongs to an account. Each statement month has an invoice.
- A card has one settlement setting. With "I confirm each invoice payment"
  on, an invoice stays open until a payment is recorded. With it off, the
  invoice is paid from the account on its due date.
- A transfer moves an amount between two accounts of the same currency.

### Investments

- An investment has a name, an institution and one of two kinds. A *balance*
  is one amount that grows, for example savings or a fund. *Units and price*
  is a quantity with a unit price, for example shares.
- An investment can start with what it already holds. That opening balance
  moves no money.
- **Value today** is one field. For a balance, the owner types the balance of
  today and the increase is saved as a yield. For units, the owner types the
  unit price of today. A lower balance is refused: it needs a withdrawal.
- A deposit takes money from an account, and a withdrawal returns money to
  one. The account has the currency of the investment. A withdrawal cannot
  exceed what the investment holds on its date.
- Units without a recorded price are valued at their cost.
- An operation can be undone when the later operations stay valid.
- An investment without operations can be deleted. One with operations can be
  archived: it leaves the Wallet grid, accepts no new operation and still
  counts in the net worth.

## Plan

Plan is one page for what the owner intends. It shows the current month.

### Limit of the month

- The limit is what the owner intends to spend in a month. It holds from the
  month in which it is set until the owner changes it. The months before keep
  the value that they had.
- **Left** is the limit minus the expenses of the month. The expenses use the
  rule of Home: the billed month, with the repeating entries that the month
  still expects.
- For the current month, the page also divides what is left by the days from
  today through the end of the month.
- The limit is in the currency of totals. Entries in another currency do not
  count.

### Category budgets

- A budget is a limit for one expense category. It counts the category and
  its subcategories, and it holds from its month on, like the limit of the
  month.
- The page offers the top-level categories that have expenses and no budget,
  with the average of the three months before.
- A budget does not change the limit of the month. The two are compared with
  the expenses separately.

### Goals

- A goal has a name, a target amount, a currency and an optional date.
- A goal counts money that exists. The owner reserves a part of a balance
  for it: of an account, or of a balance investment. A reservation moves no
  money. A goal has one reservation for each balance.
- The active goals cannot reserve more than the positive balance. When a
  balance later falls below its reservations, each goal gets a share in
  proportion to its reservation.
- **Saved** is the reserved amount that the balances cover, in the currency
  of the goal. A reservation in another currency needs an exchange rate.
- With a later date, the goal shows what each month from now through that
  date must add. A goal whose date passed says so.
- An archived goal keeps its record and frees its balances. A goal can be
  deleted.
- A balance with a reservation keeps its currency. An investment with a
  reservation also keeps its kind.

### Months ahead

- The page shows the cash of the current month and the five months after it:
  income, expenses, their result and the balance of the accounts at the end
  of each month.
- It counts what the records already expect after today: repeating entries,
  entries with a later date, card invoices on their due date, and months that
  wait for confirmation. An amount that is already late counts in the current
  month. A transfer between accounts does not count.
- The first balance is the balance of the accounts today. Amounts are in the
  currency of totals, with the exchange rate of today. An amount without a
  rate is left out and its currency is named.

### Sheet

- The sheet is the same reading as a table: one row for each source, one
  column for each month, for 6 or 12 months.
- A typed value replaces the recorded value of a cell in the sheet only. An
  emptied cell returns to the recorded value. The owner can add rows; an
  added row has one amount for each month.
- The sheet shows the balance with the changes and the balance without them.
- A sheet can be saved under a name. A saved sheet stores the changes only,
  so it follows the records when it opens again.
- Nothing in the sheet creates or changes a financial record.

### Calculators

- **Net salary (CLT)** gives the net pay of a Brazilian employee from the
  gross salary: INSS, income tax, optional deductions, the 13th salary, the
  vacation month, the year and the FGTS deposit. It uses the tables of the
  current year, or the latest ones and says so. Tables exist for 2026.
- **Compound growth** gives a balance after a count of months, from an
  initial amount, a contribution for each month and a rate for each month or
  each year.
- A calculator reads no record and saves nothing.

## Home

The owner shows, hides and orders the blocks.

| Block | Shows | Opens |
|---|---|---|
| Left to spend | With a limit of the month: what is left of the limit. Without one: income minus expenses of the month | The month window |
| Where the money went | Expenses by top-level category | The month window |
| Due soon | Invoices and months of repeating expenses that are overdue, waiting for confirmation or due within 45 days | The invoice or the monthly schedule |
| Net worth | The net worth of today and its change since the end of the month before | The net worth window |
| Goals | The active goals with what each one holds and still needs | The goal |

The month window shows a month, the six months that end with it, and the
categories with their subcategories. Its month changes inside the window.

**Net worth** is accounts plus investments, less the card debt. Card debt is
every card purchase made and not paid yet, with its later installments; a
repeating purchase counts from its date in each month. The net worth window
shows these parts and the last twelve month ends. Amounts are converted to
the currency of totals. An amount without an exchange rate is not counted,
and the window names its currency.

Above the blocks, one line tells the owner about the habit of recording: the
records are up to date on the day of an entry and the day after. From the
second day without an entry, the line says how many days passed and offers
Add. The day that counts is the day of recording, not the date written on
the entry.

## Languages and formats

The interface is in English and Brazilian Portuguese. An amount is written
the way its currency writes it, in either language. The owner chooses the
date order.

## Not built yet in 2.0

These areas exist in 1.x and are planned for 2.0. Their domain code is not in
this branch yet, except where noted.

| Area | State |
|---|---|
| Automatic alerts of 1.x (duplicates, subscription increases, cash shortage) | Not planned for 2.0. A budget and a goal show their own state |
| Loyalty points and miles | Domain moved, no API or screen. A deposit paid with points waits for it |
| Accounts in other currencies and exchange rates | Domain moved; the screens create BRL accounts only, and no screen records a rate. An investment can have another currency |
| Statement import (CSV, OFX) | Models and parsers moved, no API or screen |
| Balance checks (reconciliation), invoice credits | Domain moved, no API or screen |
| Investment fees, and the edit of a recorded operation | Domain moved, no screen. An operation is undone and recorded again |
| Month closing | Not built |
| Public site with the demonstration | Not built; `preview/` is the 1.x page |
