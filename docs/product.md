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
| Wallet | What do I have and what do I owe? | Accounts by bank, credit and debit cards, invoices, transfers, investments, points and miles, accounts in other currencies |
| Plan | What do I intend? | The limit of the month, category budgets, goals, the months ahead, the sheet, calculators and the month closing |

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
- The amount is written with its separators while it is typed: 2000 is
  2.000, and 2.000,00 when the field is left. Every field for an amount of
  money does the same.
- The account or card and the category are chosen from a list with a
  search box. The date is chosen in a calendar.
- Three options are in view under the date: repeat every month, pay in
  installments (for a credit card) and a note. Each one shows its field when
  it is on.
- A credit-card purchase can be paid in installments. Each installment counts
  in the month of its statement.
- An entry can repeat every month, with an optional last month. A repeating
  entry on an account can ask for a confirmation of each month; an unconfirmed
  month does not change the account balance.
- The amount of a repeating entry with past months changes in its monthly
  schedule, from a chosen month. Past months stay as they were.

### Categories

A category has a name, an optional type (expense or income) and an optional
parent. Settings and the menu of Transactions open the list. The list is
exported to a CSV file and imported from one, with the columns `name`,
`transaction_type` and `parent_category`. An import creates the names that
the owner does not have and changes nothing else, so the export of one
installation is the import of another. A file has at most 2 MiB and 500
rows, and a name at most 100 characters.

### Statement import

The menu of Transactions ("More actions") has **Import statement**, for an
OFX or CSV file of one account (at most 2 MiB and 500 rows). It reads OFX
with an SGML header in Windows-1252 and with a decimal point or comma, and
CSV with a comma, a semicolon or a tab, also when the file has lines before
its header.

1. **Read.** The owner chooses the account and the file. Nothing is recorded.
   The same file again opens the same import.
2. **Columns** (CSV only). The application proposes the columns of date,
   description and amount from the names in the file, with the date format
   and the decimal mark. The owner confirms or changes them.
3. **Review.** Each row needs one decision:

   | Decision | Effect at the confirmation |
   |---|---|
   | Create an entry | An income or an expense on the account, with the chosen category |
   | Already recorded | Nothing. The row is tied to a recorded movement with the same date, direction and amount |
   | Payment of a card invoice | A confirmed payment of an invoice that waits for one |
   | Transfer between my accounts | A transfer with the other account |
   | Skip | Nothing |

   A first decision is already chosen where the records give one: a bank
   identifier that was imported before is skipped, a row that equals one
   recorded movement is matched, and a description that was recorded before
   gets the category of that entry. The owner can change it.
4. **Confirm.** Every reviewed row is recorded at once, or none is. With a
   balance of the statement, the result says whether the records agree.
5. **Undo.** A confirmed import can be undone while its records are
   unchanged.

An account with an opening balance needs the date of that balance before the
review: without it, an imported row could count an amount twice.

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
- A debit card belongs to an account too. An entry paid with it leaves the
  account on its date; the card only names how it was paid.
- A card has one settlement setting. With "I confirm each invoice payment"
  on, an invoice stays open until a payment is recorded. With it off, the
  invoice is paid from the account on its due date.
- A transfer moves an amount between two accounts. Between two currencies,
  the owner types the amount that left and the amount that arrived.

### Analysis of one item

The window of an account, of a credit card and of an investment has
**Analysis**. It opens above that window and covers the twelve months to the
current one.

| Item | Shows |
|---|---|
| Investment | The value at each month end; the deposits, withdrawals and yields of each month; the gain of the units held |
| Account | The balance at each month end; what entered and left in each month; the change of the period |
| Credit card | The statement of each month; what the card owes today; the categories where it was used |

Each analysis ends with the item beside every item of its kind: its value
of the total (for example R$ 100 of R$ 1,000 invested), one bar that compares
the two, and the list of the items with the part of each. The comparison is
in the currency of totals.

### Other currencies

- An account has a currency, chosen when it is created. It does not change
  after that. Entries and balances stay in the currency of their account.
- An exchange rate is typed by the owner in Settings: one unit of a currency
  in the currency of totals, for a date. The application calls no outside
  service.
- A total in the currency of totals uses the latest rate on or before its
  date. Without a rate, the amount is left out and the screen names the
  currency and links to the rates.

### Points and miles

- A program has a name and a unit that the owner names (points, miles). The
  Wallet shows the programs after the investments. Without a program it shows
  one link to add the first.
- The owner records points earned, used and expired. Points cannot go below
  zero.
- A redemption takes points from the program and adds an amount to an
  account, in the currency of the account.
- An entry can be undone. The undo of a redemption returns the points and
  removes the amount from the account. Points that later entries use are not
  removed.
- Points are not money: they do not count in the net worth.

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

### Month closing

The closing is a short review of one month. Home asks for it while the month
before the current one is not closed, and Plan has a link to it.

1. **Balances.** For each account, the owner can type the balance that the
   bank shows on the last day of the month (or today, for the current
   month). The window shows the difference to the recorded balance. The owner
   can record what is missing, or ask for one adjustment that makes the
   recorded balance equal to the bank. An adjustment is not income and not an
   expense, and it can be removed. An empty field skips the account.
2. **Result.** The income, the expenses and their difference; the limit of
   the month; the net worth at the end of the month and its change; the
   largest categories; and what the month left open (overdue invoices and
   months that wait for confirmation).
3. **Next limit.** The limit from the month after. An empty field keeps it.

Closing records the month with the totals that the owner saw. It locks
nothing: the entries of a closed month can still change. When they change,
Home says that the month changed after its closing, and the owner reviews it
and closes it again. A closed month can be reopened. The window moves to
another month in place.

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

A second line appears while the month before waits for its closing, or
changed after it.

### Analysis

**Analyze**, beside the title of Home, opens the analysis of a period of
months. It answers four questions, each with a chart and its figures.

| Section | Shows |
|---|---|
| Income and expenses | The totals and the result of the period, the expenses for each month, and one pair of bars for each month |
| Where the money went | The top-level categories, largest first, with the part of the expenses that each one takes. One category opens month by month |
| Net worth | The net worth at each month end, with accounts, investments and card debt |
| Investments | The value against the cost at each month end, and the positions at the end of the period with the part of each one |

Each section is a block with its name in a band at the top. A bar with the
four names stays at the top of the window: a press goes to a section, and
the bar marks the section in view.

The owner chooses the period with a preset (3, 6 or 12 months, this year,
all) or with the two handles of a slider, and moves it one month at a time.
A handle follows the pointer and comes to rest on the nearest month. Each
month is a dot on the track; the dot where a moving handle will rest is lit
and has the name of its month, and the positions of the presets have their
names under the track. The track covers the records and twelve months at
least. A period ends at the current month at the latest and has at most 60
months. The address keeps the period.

In each chart:

- Under the pointer, a label with the values of one month floats above the
  plot. It does not cover the marks.
- A click on a month opens the origin of its values in a window above the
  analysis: the entries of the month (or of one category), the accounts,
  investments and card statements of the month end, or the investment
  operations of the month. Each row opens its record in the place of that
  window. Back or Escape returns to the origin, then to the analysis, which
  keeps its period.
- A drag over months gives the figures of those months: the income, the
  expenses and the result, the amount of the category, or the change of the
  net worth or of the investments from the first month end to the last one.
  "Use as the period" makes those months the period. With the pointer on
  the selected months, the label shows the same figures. Escape or a press
  outside the chart ends the selection.

Each total comes with its change against the period before, which has the
same length. When the period before starts before the oldest record, no
change is shown, and the window says so. The current month is not over: its
bars are lighter and have a dashed edge.

Income, expenses and categories are in one currency; with records in two
currencies the owner chooses one. Net worth and investments are in the
currency of totals. The month ends use the same rules as the net worth
window.

## Languages and formats

The interface is in English and Brazilian Portuguese. The owner chooses the
date order and how numbers are written: 1.234,56 or 1,234.56. The choice
holds for every amount, percentage and quantity that is shown, and for every
amount that is typed. An amount keeps the symbol of its currency and the
place of that symbol. A new owner starts with 1.234,56.

In a field for an amount, the two separator keys keep the meaning of the
choice. With 1.234,56, the point groups thousands and the comma starts the
decimals: "2.000,50" typed key by key is two thousand and fifty cents, and
"12.5" is one hundred and twenty-five. With 1,234.56 the keys change places.
A typed thousands separator shows at once, and Backspace deletes a typed
separator alone.

## The public page

The public page (`site/`) runs this application in the browser with the data
of a fictional owner. It is read-only: a save is refused with a message, and
nothing leaves the browser.

## Not in 2.0

These parts of 1.x have no screen in 2.0.

| Area | State |
|---|---|
| Automatic alerts of 1.x (duplicates, subscription increases, cash shortage, goals behind) | Not planned for 2.0. A budget and a goal show their own state |
| An entry divided between categories (a split) | Domain moved, no API or screen. The reads count a split in each of its categories |
| Points bought with an account or a card, IOF on a redemption, a deposit paid with points | Domain moved, no screen. Not planned for 2.0 unless asked |
| Invoice credits | Domain moved, no API or screen |
| Investment fees, and the edit of a recorded operation | Domain moved, no screen. An operation is undone and recorded again |
