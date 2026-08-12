# `dashboard`

The dashboard composes banking cash, categorized cash flow, card liabilities,
investments and historical FX. It owns no model and never treats raw transaction
amounts as an account ledger.

## Overview

The main screen presents:

- available balance by bank account in native currency;
- consolidated available balance in the user's base currency;
- monthly income and expenses, excluding own transfers and investment cash legs;
- open credit-card invoices and upcoming due dates;
- investment value and net worth;
- a forward outlook from recurring transactions and scheduled invoice payments.

Every converted figure identifies its valuation date. Missing rates leave native
amounts visible and produce an explicit incomplete-total warning.

## Accounting rules

`BankMovement` is authoritative for available cash. PIX and debit movements
appear immediately. Credit purchases appear in expense analysis and invoice
liabilities, but not in account balance. On the due date, the invoice's single
payment movement reduces available cash and clears the liability; it does not
create another expense.

Own-account transfers are visible in account ledgers but net to zero in
consolidated cash and are excluded from income/expense. Cross-currency transfers
use the historical rate stored with the paired movement.

Investment deposits and withdrawals move cash between banking and the portfolio
without becoming income/expense. Yield affects investment value internally; it
does not increase available bank balance.

## Reports

Reports retain server-rendered SVG/CSS and HTMX-enhanced filters with plain GET
fallbacks. The approved report set is organized by source of truth:

1. Available cash evolution from account opening balances and movements.
2. Monthly income and expense from categorized transactions.
3. Spending by category and settlement instrument.
4. Credit-card invoice evolution, due dates and paid/open status.
5. Native-currency balances plus historical base conversion.
6. Net-worth evolution combining bank cash, investments and open invoices.

Charts must label actual versus projected values. Forecasts may include future
recurrences and invoices but must not post them or alter today's ledger.

## No-double-counting checks

- Never subtract a credit purchase from available cash before invoice payment.
- Never count an invoice payment as a second expense.
- Never count both sides of an own transfer as income/expense.
- Never classify investment deposit/withdrawal as consumer cash flow.
- Never convert a historical event using the latest rate when an effective-date
  rate was captured.
