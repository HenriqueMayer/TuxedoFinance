# Salary sandbox

The authenticated `/sandbox/clt-pj/` page is a non-persistent estimator for a
Brazilian service professional comparing CLT and PJ compensation. It is not a
financial ledger and never reads or writes transactions, accounts, investments,
sessions, or user preferences.

## Calculation boundary

The first catalog is the 2026 rule set. It contains official source URLs and a
review date. The calculator covers employee INSS/IRRF, FGTS, 13th salary,
vacation with one-third, employer profiles, Simples Nacional Annexes III/V,
Lucro Presumido, pró-labore, operating costs, dividend withholding, and a
bidirectional annualized comparison. The IRRF calculator automatically selects
the legal or simplified deduction that produces the lower taxable base.
Runtime calculation never searches the internet.

## Interaction model

The interface has three explicit POST states: `select`, `calculate`, and
`compare`. The initial response shows only the CLT and PJ path cards, with no
default selection. Selecting a path reveals only its inputs and the monthly
plan. Switching paths preserves the common planning inputs but invalidates the
calculation and comparison. The fixed-cost target accepts either BRL or a
percentage and reports both the calculated amount and its percentage of
normalized net income. Suggested percentages and up to 20 request-local custom
categories can be entered before calculation; clearing estimates removes all
of them.

After the selected income is calculated, a direction-specific action solves
the other income: “See comparison with PJ” from CLT and “See comparison with
CLT” from PJ. Equivalence uses the complete annual package, while the same
monthly plan is applied to both normalized incomes for a disposable-budget
comparison. Employer profile, RAT/FAP, and third-party contributions belong to
the PJ-to-CLT comparison because they affect employer cost, not employee
payroll deductions.

Only the selected scenario has required inputs. PJ history and employer or
operating assumptions remain in accessible optional sections. Starting-company
defaults let a first-month Simples estimate work without asking for an
inapplicable RBT12 history.

Every sandbox input and calculated metric has a short bilingual help popover.
Hover or keyboard focus previews it beside the information icon, while click
keeps it open. Only one popover remains open, and a second click, outside click,
or Escape dismisses it. Escape restores focus to the trigger. Positioning is
recalculated against the viewport so help inside scrolling tables is neither
clipped nor moved to the bottom of the page.

The result is an explainable estimate. It does not replace professional advice
or calculate CNAE eligibility, collective bargaining agreements, municipal
special regimes, annual high-income minimum taxation, complete annual IRPF,
Lucro Real, MEI, or real financial postings.

## Privacy and request flow

Inputs are submitted by POST and are not placed in the URL. HTMX replaces the
single `#sandbox-workspace` island. Its fragment marker is submitted as form
data, so partial rendering does not depend on request headers inherited from
the application shell. A regular form POST remains the complete fallback. The
app has no models or migrations, and no scenario or custom variable is retained
after the page request.
