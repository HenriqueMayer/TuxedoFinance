# Invoice credits and opening installments — 2026-10-20

This dated review records the native credit/opening-installment change. Current
contracts live in [Banking](../apps/banking.md#invoice-credits),
[Transactions](../apps/transactions.md#opening-installment-purchases),
[the data model](../data-model.md) and [the interface map](../interface-map.md).

## Scope

- Add an owned credit source with an explicit statement month, positive
  magnitude, posting date, expense category and idempotent confirmation.
- Keep invoice net totals, debt/assets, expense reports, category budgets,
  source links and simulation snapshots coherent without manufactured cash.
- Preserve late-credit settlement evidence and posting-date cutoffs.
- Track only remaining installments of an opening purchase while retaining the
  original date, source total, full installment count and actual numbering.
- Provide shared entry/error/delete forms, keyboard/native paths, Portuguese
  and English strings, and desktop/phone layouts in both themes.

## Validation

- The complete isolated Django suite passed **1,236 tests** after correcting a
  zero-FX obligation regression: stored manual invoices without source rows
  must retain their registered amount.
- Focused final checks covered posting cutoffs, payment limits, legacy invoices,
  category protection and opening installments. An additional 18-test run
  checked dated wealth after the final opening-month guard.
- **44 distinct focused browser cases passed** across credit entry/edit/delete,
  partial-plan recovery, transaction filters, category splits and confirmed
  payments. Coverage includes desktop/phone, light/dark, EN/PT-BR, keyboard and
  native no-JavaScript submission. Long names, invalid responses, final actions
  and fixed navigation were visually inspected in synthetic captures.
- JavaScript unit tests: **26 passed**. Focused executable-correctness lint,
  Django checks/migration drift, CSS reproducibility, translation compilation
  and `git diff --check` passed. Documentation validation found 89 documents,
  763 local references and no unresolved links.
- A private-copy opening import produced the owner-approved invoice amount;
  repeating it inserted no duplicates. Earlier settled installments produced
  no historical invoices or cash debits, and unrelated tables remained equal.

Browser fixtures use synthetic data and their own disposable database. These
focused browser runs are not a claim that the full browser suite was executed.
Private owner import values and evidence remain outside tracked documentation.

## Data and delivery boundaries

The separately authorized owner import is rehearsed against a private copy,
with atomic assertions, duplicate-import checks and a pre-write backup. Existing
accounts, cards, categories, other-user data and source evidence are preserved.
The authorized local import completed after an updated backup and the two
additive migrations. A read-only comparison preserved existing rows in 43
protected tables; only the new model content type/permissions were added to
authentication metadata. Repeating the import created no additional records,
and SQLite integrity passed. The developer runtime resumed after the brief
write window.

Raw merchant data, owner identifiers, private backup paths and import scripts
stay ignored/local. No statement-upload route, bank connection, AI call, commit
or publication is enabled by this work.

Excess credit stays on its assigned card/month and is visible as a card asset;
there is no automatic carry-forward to another month. A credit source does not
claim to identify an original purchase without explicit matching evidence.
