# `dashboard`

The dashboard composes banking cash, categorized cash flow, card liabilities
and investments. It owns no model and never treats raw transaction amounts as an
account ledger.

## Overview

The main screen presents:

- a live available-cash total and compact native balances by bank account;
- selected-month opening, balance change and closing balance;
- income, expenses, investment deposits and withdrawals for the selected month;
- a top-six categorized-expense breakdown;
- compact open-invoice previews and upcoming due dates;
- a six-month outlook from recurring transactions and scheduled invoice payments.

For the current month, performance is split at the local current date. One-off
transactions use their recorded date, fixed recurrences keep their configured
day (clamped to the target month's last day), and installments remain known
obligations from their original purchase. Investment and loyalty events use
their own event date. The portion after the cutoff is shown as planned. Past
months are complete; future months are entirely planned. Category totals follow
the same current/past/future rule.

Per-user base currency is implemented through `UserPreference`. Historical
investment operations consume their persisted FX evidence; account balances,
transactions and movements still use explicitly current/read-time conversion.

## Accounting rules

`BankMovement` is authoritative for available cash. PIX and debit movements
appear immediately. Credit purchases appear in expense analysis and invoice
liabilities, but not in account balance. On the due date, the invoice's single
payment movement reduces available cash and clears the liability; it does not
create another expense.

Own-account transfers are visible in account ledgers but net to zero in
consolidated cash and are excluded from income/expense.

Investment deposits and withdrawals move cash between banking and the portfolio
without becoming income/expense. Yield affects investment value internally; it
does not increase available bank balance.

The dashboard keeps economic performance distinct from cash settlement. Income,
expenses and the selected month's projected closing describe activity assigned
to the month. Available cash and the current month's through-today cash change
come from posted account movements. Card purchases therefore stay in their
statement month while actual account cash changes when the invoice is settled.
The live account and open-invoice panels always describe today, even while
another month is selected.

## Reports

Reports retain server-rendered SVG/CSS and HTMX-enhanced filters with plain GET
fallbacks. The approved report set is organized by source of truth:

1. Available cash evolution from account opening balances and movements.
2. Monthly income and expenses from categorized transactions, with investment
   deposits and withdrawal credits shown as separate cash-flow series.
3. Spending by category and settlement instrument.
4. Credit-card invoice evolution, due dates and paid/open status.
5. Currency-aware balances with persisted investment-operation snapshots and
   clearly labeled current/read-time valuations for entities not yet covered.
6. Net-worth evolution combining bank cash, investments and open invoices.

Charts must label actual versus projected values. Forecasts may include future
recurrences and invoices but must not post them or alter today's ledger.

## No-double-counting checks

- Never subtract a credit purchase from available cash before invoice payment.
- Never count an invoice payment as a second expense.
- Never count both sides of an own transfer as income/expense.
- Never classify investment deposit/withdrawal as consumer cash flow.
- Do not silently treat unlike currencies as equal. Historical transfer and
  investment totals use persisted FX snapshots; missing conversion is explicitly
  incomplete elsewhere.
