# Planning and saved scenarios

The authenticated `/sandbox/` workspace contains a simple monthly salary plan
and the hypothetical investment simulator. Existing
URLs remain valid. Calculations read financial sources without synchronizing or
posting ledger entries. Only an explicit save, duplicate or delete changes the
user's `ScenarioDraft` records.

## Salary and monthly budget

The user enters a gross monthly salary and selects one month. The workspace reads
that month's existing expense forecast from one-off, recurring, installment,
points-purchase and redemption-IOF records, then shows the forecast in a single
card. Changing the month refreshes the card; the explicit button provides the
same path without JavaScript.

Up to 20 additional fixed BRL expenses may be added for amounts that are not
already recorded. The result subtracts the existing forecast and those added
amounts from the gross salary. Negative remainders stay visible. Invalid rows are
retained for correction, and add/remove controls work through ordinary POSTs
without JavaScript.

The salary plan no longer asks for payroll deduction modes, CLT details,
percentage targets, reserves or investment allocations. It does not add the
hypothetical salary to real bank balances.

## Drafts and privacy

`ScenarioDraft` stores owner, name, kind, input payload and created/updated times.
Payloads include schema/calculation versions, original input format,
completion state and an optional dated expense snapshot. Valid values have a
canonical representation; invalid input remains recoverable. Incomplete drafts
are allowed but never display a projected total as if calculation succeeded.

Save, open, duplicate, delete and compare up to three drafts through `/sandbox/drafts/`.
All lookups are owner-scoped. Inputs use POST rather than query strings. There is
no autosave: calculating or changing the selected month never saves. Saving is
kept in an explicitly optional disclosure. As elsewhere in the app,
shared presentation context may initialize missing user preferences; it does not
create financial records.

## Investment simulation

The simulator accepts currency, opening balance, first month, duration (1–120 full
months), an effective monthly or annual rate and recurring contributions and
withdrawals. A table allows per-month overrides; an empty cell uses the default,
and zero explicitly overrides it.

Inputs are grouped in reading and Tab order: starting point, rate and duration,
then monthly movements. Individual-month overrides remain in a native disclosure,
opened on saved overrides, validation errors or a native Update month rows action.
With JavaScript, changing duration updates rows immediately. Temporarily excluded
rows retain edits but are hidden and disabled; extending the duration restores them.
The server still validates and calculates only the submitted duration.

Results lead with totals; the monthly breakdown is an optional disclosure whose
open state survives live recalculation. Saving is offered after the result in a
separate disclosure, opened for an existing draft or naming errors. Calculation
never requires a draft name. All three stages, overrides, calculation and saving
remain usable without JavaScript.

For each month, yield is calculated on its opening balance and rounded to cents.
Contributions and withdrawals occur at month end, so a contribution earns from
the following month. Annual rates use Decimal compound equivalence,
`monthly = (1 + annual / 100) ** (1 / 12) - 1`. Results show opening and closing
balances, contributions, withdrawals and estimated yield. Non-finite values,
unsupported amounts and withdrawals exceeding available funds are rejected.
Taxes, inflation, CDI and real market returns are not inferred.

JavaScript recalculates only the result region, preserving the active input and
viewport. The Calculate button remains a complete no-JavaScript path. Simulations
never create investment operations, bank movements or categorized transactions.
Market prices, price histories, agent integration and free-form formulas remain
[roadmap work](../product-requirements.md).

## Interaction contracts

Forms reuse shared fields, native short choices and help popovers. Dates follow
the user's DMY/MDY preference; month inputs explicitly use `YYYY-MM`, independently
of that preference. ISO dates remain the storage and technical contract.
Follow the [form and keyboard contract](../frontend.md#keyboard-and-choice-contract),
[question-mark help contract](../frontend.md#question-mark-help), and
[viewport-preservation contract](../frontend.md#preserve-the-users-location).
