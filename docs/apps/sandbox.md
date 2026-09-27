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
card. New forecasts use the economic reference month, matching the Report:
credit-card installments and recurring expenses belong to their statement month,
even when the invoice is payable next month. Account expenses keep their own month.
Invoice settlement is not counted again. Points purchases and redemption IOF
remain included in planning. Amounts remain BRL snapshots at capture time.
Existing saved drafts retain their captured payment-month basis until recalculated;
opening or comparing a draft does not silently change its values.

Changing the month refreshes the card. Clicking anywhere on the native month
field opens its picker when supported; previous/next buttons submit the entire
form and cross year boundaries while retaining unsent salary and expense rows.
A localized month/year caption makes the chosen period explicit. The forecast
button is available only without JavaScript, where it provides the native refresh
path. Forecast changes never save a draft.

New plans start with editable Emergency reserve and Investment rows, both in
BRL with a zero amount so they do not assume an allocation. They support the
same currency/percentage choice and removal as other rows. Defaults appear only
on the initial new-plan GET; month changes, invalid submissions and saved drafts
preserve the user's rows without reintroducing removed suggestions.

Up to 20 additional expenses may be added for amounts not already recorded.
Each row accepts either BRL or a percentage (0–100) of the gross monthly salary,
not of the remainder after other expenses. Percentages use Decimal arithmetic
and each result is rounded to cents. The existing draft payload retains the
selected unit and raw invalid input. The result subtracts the existing forecast
and those added amounts from the ordinary monthly CLT net salary. Negative remainders stay visible. Invalid rows are
retained for correction, and add/remove controls work through ordinary POSTs
without JavaScript.

CLT deductions are automatic: progressive employee INSS up to its ceiling and
IRRF with the more favorable legal/simplified deduction and the 2026 reduction.
The result displays gross salary, INSS, IRRF and ordinary monthly net salary.
The optional Adjust CLT parameters disclosure accepts dependents, legally
deductible alimony, transport cost (employee deduction capped at 6% of gross),
food, health and other payroll deductions. All default to zero. Alimony reduces
the legal IRRF base and is withheld from net pay exactly once. Food, health and
other deductions only reduce take-home pay, not the monthly IRRF base.
Parameters survive month changes, errors and explicit draft saving/comparison;
invalid fields reopen the disclosure, including without JavaScript.

Consult INSS and IRRF brackets submits the current inputs without saving a draft
and reveals the tables beneath the result. The INSS highlight is the marginal
gross-salary band (the last band also represents salaries above the ceiling);
lower portions remain taxed progressively. The IRRF highlight uses the calculated
taxable base after the more favorable deduction, not gross salary. A separate
gross-income table explains the 2026 reduction and shows the applied reduction.
Highlights use text as well as color, and official source links are included.
The settings and bracket disclosures retain their state through HTMX updates.
The plan does not add vacation pay, thirteenth salary or employer FGTS to a normal month.
The UI explicitly identifies the 2026 rule set, also when projecting another year;
it does not claim to have that other year's tax table. The source tables are
[INSS](https://www.gov.br/inss/pt-br/direitos-e-deveres/inscricao-e-contribuicao/tabela-de-contribuicao-mensal)
and [Receita Federal](https://www.gov.br/receitafederal/pt-br/assuntos/meu-imposto-de-renda/tabelas/2026),
verified on 2026-09-27.

Budget drafts saved with calculation version 1 retain their gross-based result
when opened or compared, with an explicit notice. A deliberate calculation uses
CLT, and an explicit save records calculation version 2. Percentage expenses
continue to use gross salary in both versions. The plan does not add the
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
then monthly movements. The starting month uses the native month picker. The
rate period precedes the rate, whose label specifies monthly or annual; changing
it reinterprets the entered effective rate rather than converting it. Monetary
labels reflect the selected currency. Optional keyboard-accessible duration
shortcuts select 6, 12, 24 or 60 months, retain focus and reuse the same validated
1–120 month field and live calculation. Native forms keep all parameters editable.
Individual-month overrides remain in a native disclosure,
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
the user's DMY/MDY preference; month controls display the browser's locale and
submit `YYYY-MM`, independently of that preference. Invalid month text is
rendered as a text field after a rejected submission, so it remains recoverable. ISO dates remain the storage and technical contract.
Follow the [form and keyboard contract](../frontend.md#keyboard-and-choice-contract),
[question-mark help contract](../frontend.md#question-mark-help), and
[viewport-preservation contract](../frontend.md#preserve-the-users-location).
