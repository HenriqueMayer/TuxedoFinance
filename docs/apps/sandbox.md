# Planning and saved scenarios

The authenticated `/sandbox/` workspace contains the salary calculator, monthly
planning, future commitments and the hypothetical investment simulator. Existing
URLs remain valid. Calculations read financial sources without synchronizing or
posting ledger entries. Only an explicit save, duplicate or delete changes the
user's `ScenarioDraft` records.

## Salary and monthly budget

The user enters one gross monthly salary and chooses between:

- **Automatic CLT:** the versioned 2026 employee INSS and IRRF rules, including
  the most favorable monthly IRRF deduction, vacation with one-third, 13th salary,
  FGTS, annual net income and normalized monthly net income.
- **Manual:** deductions entered as BRL amounts or percentages of gross salary.
  Annual projection repeats the resulting month twelve times; it does not infer
  benefits, extra payments or tax rules.

The automatic catalog was reviewed on 2026-09-02 against the official
[INSS contribution table](https://www.gov.br/inss/pt-br/direitos-e-deveres/inscricao-e-contribuicao/tabela-de-contribuicao-mensal),
[2026 Receita Federal tables](https://www.gov.br/receitafederal/pt-br/assuntos/meu-imposto-de-renda/tabelas/2026),
and [FGTS rules](https://www.fgts.gov.br/Paginas/sobre-o-fgts/regras.aspx).
Values, sources and the review date are versioned in `sandbox/tax_rules/y2026.py`.
Runtime calculation never searches the internet.

The monthly budget has two expense bases. **Free estimate** uses fixed costs in
BRL or as a percentage of take-home pay. **Recorded commitments** replaces that
aggregate with the selected month's captured obligations; it does not add them
again to the fixed-cost percentage. Additional expense rows represent extra
hypotheses. Emergency reserve and investment targets remain percentages.
Negative remainders stay visible.

Manual payroll deductions and additional expenses are separate lists, with a
maximum of 20 rows each. Invalid or excessive input is rejected explicitly and
retained for correction. Add/remove controls also work through ordinary POSTs
without JavaScript.

Salary planning uses BRL. The separate real-resources section uses the user's
base reporting currency and the shared Banking availability service. Hypothetical
salary is never added to a bank balance that may already contain it. Reserves,
excluded accounts and redeemable cash pots therefore have the same meaning in
Banks, Overview and Planning.

## Future commitments

Capture builds a read-only 12-month snapshot from the selected month. It expands
one-off expenses, recurring expenses, installments, points purchases and redemption
IOF by payment date. Card items follow invoice due dates; invoice totals are not
added a second time. Rows identify source, installment, instrument, native currency
and amount. Conversion to BRL is frozen at capture, with missing exchange rates
explicitly incomplete. A user may exclude a row or supply a hypothetical BRL
amount without editing its source.

Refreshing requires a preview and explicit Apply action. Stable source/occurrence
identifiers retain manual amounts and exclusions when dates or amounts change.
Removed sources remain marked until the user excludes them. Capturing or reviewing
changes does not silently replace a saved draft. The signed snapshot is bound to
its owner; recalculating cannot accept another user's snapshot.

A snapshot holds at most 2,000 obligations across its 12 months. Capturing or
merging beyond that limit returns a visible error and keeps the previous snapshot;
it never silently truncates obligations. The finite request field limit of 10,000
supports every editable row without JavaScript. Django's default 2.5 MB request
body limit remains in effect.

## Drafts and privacy

`ScenarioDraft` stores owner, name, kind, input payload and created/updated times.
Payloads include schema/calculation versions, original input format, tax-rule year,
completion state and an optional dated commitment snapshot. Valid values have a
canonical representation; invalid input remains recoverable. Incomplete drafts
are allowed but never display a projected total as if calculation succeeded.

Save, open, duplicate, delete and compare up to three drafts through `/sandbox/drafts/`.
All lookups are owner-scoped. Inputs use POST rather than query strings. There is
no autosave: live calculation only refreshes results. As elsewhere in the app,
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
