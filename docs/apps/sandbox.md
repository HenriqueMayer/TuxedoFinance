# Salary sandbox

The authenticated `/sandbox/` page is a small, non-persistent salary and
monthly-budget estimator. Its calculation path does not read or write
transactions, bank accounts, investments, user preferences, or scenario data in
the authenticated session. Shared template context still resolves presentation
preferences through `core.context_processors.currency`; a missing preference
may be initialized there. Scenario inputs and results remain request-local.

## Calculation modes

The user enters one gross monthly salary and chooses between two modes:

- **Automatic CLT:** applies the versioned 2026 employee INSS and IRRF rules,
  chooses the most favorable monthly IRRF deduction, and projects vacation
  with one-third, 13th salary, FGTS, annual net income, and normalized monthly
  net income.
- **Manual:** subtracts user-defined monthly deductions or taxes entered as a
  fixed BRL amount or as a percentage of gross salary. Its annual projection
  repeats the resulting month twelve times and does not infer benefits, extra
  payments, or tax rules.

The automatic catalog was reviewed on 2026-09-02 against the official
[INSS contribution table](https://www.gov.br/inss/pt-br/direitos-e-deveres/inscricao-e-contribuicao/tabela-de-contribuicao-mensal),
[2026 Receita Federal tables](https://www.gov.br/receitafederal/pt-br/assuntos/meu-imposto-de-renda/tabelas/2026),
and [FGTS rules](https://www.fgts.gov.br/Paginas/sobre-o-fgts/regras.aspx).
The review date and source URLs are versioned with the values in
`sandbox/tax_rules/y2026.py`. Runtime calculation never searches the internet.

## Monthly plan

Both modes feed the same monthly plan. Fixed costs accept either BRL or a
percentage of net income. Emergency reserve and investment targets use
percentages. Additional expenses can be entered in BRL or as percentages. The
result keeps negative remainders visible instead of hiding a deficit.

Manual deductions and monthly-plan expenses are separate lists: deductions
produce take-home pay, while expenses explain how that take-home pay is used.
Up to 20 rows from each list are accepted per request.

## Interaction and privacy

Every input and calculated metric has short bilingual help. Hover or keyboard
focus previews help beside its icon, while click keeps it open. Outside click,
a second click, or Escape dismisses it. Positioning is viewport-bound, including
inside scrolling tables.

Inputs are submitted by POST and never placed in the URL. HTMX replaces only
`#sandbox-workspace`; a regular form POST is the complete fallback. The app has
no models or migrations, and no salary, deduction, or expense is retained after
the request.
