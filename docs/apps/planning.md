# `planning`

This app owns operational category budgets, financial goals, reservations and
deterministic local review signals. It is separate from `sandbox`, whose private
drafts and hypothetical simulations do not become real budgets or postings.
These features are implemented under Unreleased after the `0.10.0` baseline.

## Category budgets

`CategoryBudget` sets a positive native limit for an owned expense-compatible
category, currency and calendar month. Months are stored on their first day.
The category includes its descendants. Overlapping ancestor/descendant budgets
in the same month and currency are rejected, as is a duplicate category limit.
Category type/hierarchy edits are also rejected if they invalidate saved limits
or introduce overlapping covered branches.
Copy previous month adds compatible missing limits without overwriting the
destination month's existing settings.

`budget_progress(user, month, *, as_of=None)` returns recorded spending through
the cutoff and a full-month forecast from known source transactions. Economic
spending follows the transaction's reference month, including installments and
fixed recurrences; it does not follow invoice-payment cash dates. Category
splits contribute their exact allocated cents. Investment cash legs and own
transfers are not categorized consumer spending.

Foreign spending is converted into the budget currency using the available
rate at the requested cutoff, capped at month end. Missing rates remain explicit
and the total is partial; spending is never treated as zero merely because a
conversion is absent. Remaining budget can be negative. These are spending
limits, not account balances, and saving them creates no movement.

## Financial goals and existing cash

`FinancialGoal` stores a name, positive target amount, target currency, optional
deadline and archive flag. Progress comes only from explicit `GoalAllocation`
rows. An allocation identifies exactly one owned bank account or one
`MONTHLY_CASH` product plus `MONETARY` asset and a positive amount in that
source's currency. A unit asset or long-term investment product cannot be
reserved as spendable goal cash.

`save_allocation` checks all active reservations for the owner against the
source's current positive balance. A source cannot be pledged twice beyond its
available backing. The save is atomic and requests an owner lock on databases
with row-lock support; SQLite still serializes writers. Goal currency is a
reporting denomination, not a currency conversion or transfer of the source.

An allocation is an earmark: it creates no movement, deposit, expense or new
asset. Banking availability sets aside the greater of an account's manual
reserve and its active named reservations, rather than adding both claims of
the same money. Cash-pot reservations reduce planning availability in their
own currency. Neither reservation reduces net worth.

`goal_progress(user, *, as_of=None, include_archived=False)` separates declared
reservations from currently backed progress. If cash is subsequently spent or
withdrawn, positive backing is apportioned proportionally in stable order with
cent reconciliation; shortages remain visible. Conversion to the goal currency
uses the requested date and exposes missing currencies. Historical cutoffs
exclude allocations created later, but use the current saved goal/allocation
definitions: this is not an immutable history of prior target or reserve edits.

Archiving a goal releases its active reservations without deleting their
meaning. Restoring revalidates backing against other active goals. Accounts,
products and assets remain protected by saved allocations, including archived
ones. Product purpose and asset currency/valuation mode cannot be changed in a
way that reinterprets those reservations.

## Local signals

`local_signals(user, *, as_of=None)` returns reviewable evidence and contextual
owned-source links. There is no remote service, AI inference, automatic
categorization or automatic correction. `SignalSettings` independently enables
four heuristics and stores their thresholds:

- Possible duplicates: equal normalized description, payment instrument,
  currency and amount within a configurable window up to 14 days (default three;
  zero limits matches to the same day).
- Possible subscription increases: two similar recorded expenses 20–45 days
  apart with an increase above the chosen threshold. A pattern does not prove a
  subscription; fixed templates do not preserve a historical price series.
- Budget overspending: recorded or known month-forecast spending exceeds a
  saved category limit, with incomplete-conversion status retained.
- Future bank cash shortage: current account cash plus dated future recorded
  movements and outstanding manual invoice obligations crosses below zero
  within a configurable 1–90 day horizon.

Transaction pattern checks are bounded to the latest 1,000 eligible non-fixed,
non-generated expenses in the last 90 days and at most 100 transaction
suggestions. The screen discloses these limits. Cash-shortage checks do not
assume unrecorded income, future cash-pot withdrawals or spending of reserved
goals. Manual amounts use the unpaid remainder at the cutoff, once at their due
date or today when overdue. Already confirmed payment movements are included in
current cash and reduce that remainder, preventing a second deduction. For a
historical cutoff, later known payments remain dated cash movements on their
actual paying account and are excluded from the forecast obligation, including
late payments and payments from another owned account. Invoice
obligations remain forecast evidence and never create a synthetic cash debit.
Absence of a warning is not proof that unrecorded obligations are funded.

Acknowledging or dismissing writes only a `SignalDecision` keyed by the evidence
hash. Source changes produce new evidence rather than silently inheriting a
previous decision. Reading defaults does not persist a settings row, and no
signal alters a financial source or ledger.

## Routes, forms and isolation

`/planning/` opens budgets; `/planning/goals/` and `/planning/signals/` expose
goals and local checks. Budgets and allocations support owned create, edit and
delete flows. Goals support creation/editing and reversible archiving rather
than a destructive delete route; archiving and signal decisions are explicit POSTs.
Settings are saved only through their explicit form.

Month filters use ordinary GETs. Forms use shared field/choice rendering,
`novalidate`, Django error recovery and complete native submissions. Reservation
sources use a stable shared searchable selector, start empty and reveal the
amount only after deliberate selection. Foreign-key ownership, category
compatibility, source denomination and balance validation remain on the server.
Follow the [shared form contract](../frontend.md#keyboard-and-choice-contract).

See [banking availability](banking.md#monthly-planning-availability),
[category splits](transactions.md#category-splits) and
[sandbox](sandbox.md) for their separate accounting boundaries.
