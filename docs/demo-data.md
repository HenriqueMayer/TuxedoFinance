# Optional demonstration data

`insert_demo` creates a separate account with fictional financial records for
presentations and exploration. Run it explicitly against the installation where
you want the records. Setup, migrations, server startup and ordinary signup do
not run it. The generator does not read or copy another user's financial records.

The command is available starting with v0.9.0 in source checkouts and published
Docker images. For a Docker installation, run from its existing installation
directory:

```bash
docker compose --env-file .env.docker exec web python manage.py insert_demo pt
docker compose --env-file .env.docker exec web python manage.py insert_demo en
```

The expanded examples described below belong to the unreleased
`feat/personal-finance-evolution` source branch. The published v0.10.0 image
contains the earlier dataset. Use the [branch testing guide](branch-testing.md)
to review the new features in an isolated installation; no new image or release
is implied by this guide.

## Create the accounts

From the repository root, use the same environment as the local application.
The command writes to the configured database, including any `TUXEDO_DATA_DIR`
or `TUXEDO_ENV_FILE` selection. See [Locate the active database](operations.md#locate-the-active-database)
and the [backup procedure](operations.md#sqlite-backup) for an existing installation.
The database must already have its migrations applied.

```bash
uv run python manage.py insert_demo pt
uv run python manage.py insert_demo en
```

Each command prints the new username and a randomly generated password after
successful creation. Use those credentials in the normal login form. The default
usernames are `demo_pt` and `demo_en`; they are ordinary accounts without staff
or superuser access. No fixed demo password is shipped. To choose a new password
later, use Django's interactive command:

```bash
uv run python manage.py changepassword demo_pt
```

Both versions describe the same fictional Brazilian financial activity, with BRL
as the reporting currency and BRL, USD and EUR accounts. The language argument
sets the stored record names and descriptions. Portuguese uses DMY dates and
English uses MDY dates. It does not change the financial values, country or
payroll model.

Select Portuguese or English with the application's language switch when
presenting. Interface language is retained in the browser's language cookie,
independently of the account's date and reporting-currency preferences. Switching
the interface language does not translate stored record names.

## Date and username options

By default, dates are anchored to today. Transaction history spans thirteen
calendar months: the twelve months before the anchor month and the anchor month.
Investment operations span twelve calendar months, ending in the anchor month.
The dataset also includes scheduled commitments for later months. To create a
repeatable financial timeline or another demonstration account, pass an explicit
anchor date and an unused username:

```bash
uv run python manage.py insert_demo pt --username presentation_pt --as-of 2026-09-28
uv run python manage.py insert_demo en --username presentation_en --as-of 2026-09-28
```

`--as-of` accepts an ISO date (`YYYY-MM-DD`) with a year from 1901 through 9988,
matching the supported planning-form dates. It anchors the generated records;
it does not change the application's clock. When using an older anchor, select
that month or a historical chart window in the relevant reports to explore its
activity. **Last 12 months** is a rolling window relative to today, not the entire
ledger history. A saved
monthly plan uses the application's current payroll rule set, not a historical
tax table for the anchor year.

Known account and investment opening dates are explicit in the new dataset.
Confirmed invoice payments are created only when their dates are not in the
future. Goal allocations also require a source balance that is actually
available today: a future anchor can therefore create unfunded targets without
inventing payments or reserves. Selecting a historical report period does not
rewind the application's clock.

The command refuses an existing username, ignoring case, including an existing demo account.
It never merges into, replaces or clears that account. Creation is atomic: an
error rolls back the new account and its financial records together. Running
the command again is not a refresh operation; use another unused username for
a fresh dataset. Changes made while presenting remain saved normally.

## Presentation walkthrough

The records exercise the application's existing features. Routes below are
relative to the running application. Use the same route with either account;
the record labels follow the chosen dataset language.

| Area | Route | What to explore |
|---|---|---|
| Overview | `/dashboard/` | Current cash, monthly income and expenses, expense categories, investments, upcoming card settlements and the six-month outlook. Compare the current month with earlier months. |
| Reports | `/dashboard/reports/` | Balance evolution, monthly cash flow, installment commitments and income/expenses by account or card. Change the period and select chart values. |
| Activity | `/transactions/` and `/categories/` | Salary and additional income, household expenses, one-off purchases, fixed recurrences and installments, with categories and subcategories. Filter by category and recurrence, export CSV, or split a transaction between categories without changing its payment. |
| Banks | `/banking/`, then select a bank | Accounts in BRL, USD and EUR; PIX, debit cards and physical/virtual/additional credit cards; planning exclusions and partial reserves. Open Transfer to try moving funds between owned accounts. |
| Invoices | `/banking/invoices/` | Compare legacy automatic invoices with the synthetic confirmed-payment card: an overdue invoice and a partially paid invoice, with an explicit bank debit for its confirmed payment. |
| Loyalty | `/banking/`, then select Aurora Demo Bank or More options | The bank-linked miles program and independent cashback program have seeded balances. Open Points entry to explore awards, purchases, adjustments, expiration and redemptions, or Redeem points for a monetary redemption. |
| Exchange rates | `/banking/exchange-rates/` | Dated synthetic USD/BRL and EUR/BRL rates, with create, edit and delete actions. The sample transfers and investment operations retain their historical FX snapshots. |
| Investments | `/investments/`, `/investments/operations/` and `/investments/settings/` | Monetary and unit-based opening positions, account/points-funded deposits, withdrawals, fees and manually entered yields. Configuration includes all six asset classes and both product purposes. |
| Investment charts | `/investments/charts/` | Compare Overall, Portfolio and Remunerated cash across the investment history. |
| Local prices | `/investments/prices/` | Inspect dated, explicitly synthetic observations for the three unit assets, their historical valuations and results with known opening dates and declared fee currencies. These observations are not a market feed. |
| Budgets | `/planning/budgets/` | Compare current and previous monthly category limits, recorded spending and known forecasts; copy a month and inspect an exceeded limit. |
| Goals | `/planning/goals/` | Inspect emergency, travel and monthly-buffer targets backed by an account or monetary cash pot. The travel target uses USD; reservations reuse existing funds and do not create money or duplicate legacy reserves. |
| Signals | `/planning/signals/` | Review intentional duplicate examples, a subscription increase, an exceeded budget and a future debit shortfall. One duplicate is already acknowledged; reviewing signals never edits source records. |
| Saved scenarios | `/sandbox/drafts/` | Open and compare the two monthly plans, then open the two-year yield simulation with monthly overrides and a planned withdrawal. Edit parameters and recalculate through Monthly plan or Yield simulation. Calculations do not post real salary or simulated returns to the ledger. |
| Settings | `/accounts/settings/` | Date format and reporting currency. The interface language switch is in the account menu, and theme controls are in the navigation. |

The [net-worth and statement interfaces remain paused](roadmap.md). Demonstration
data does not enable them or add their navigation entries. Old operation URLs
return to their owning workspace; owned confirmed/undone import history remains
read-only when it exists. The generator does not upload files or seed import
batches. Underlying valuation and ledger records remain available to the active
screens described above.

The loyalty examples include an invoice award, account-funded and card-funded
points purchases, opening adjustments, expiration, and three monetary
redemptions: no IOF, account-funded IOF and card-funded IOF. The banking pages
show program balances and entry actions; they do not provide a separate loyalty
history page.

Credit-card purchases appear in their statement month. Legacy automatic cards
post cash on the invoice due date; the confirmed-payment card changes actual
cash only on a recorded payment date and retains unpaid forecast obligations.
Transfers between owned accounts are not income or
expenses. Remunerated cash and long-term investments have different effects on
monthly planning availability. These distinctions remain the same in both
datasets; the examples use the application's normal posting services.

All rates, prices, rewards and return assumptions are fictional. Local price
observations are entered explicitly, yields are recorded manually, and saved
simulations are hypothetical. The dataset does not add live market feeds,
automatic yield accrual or banking integrations. Missing dates, prices or
conversions remain visible limitations rather than fabricated returns.

## Relationship to the public preview

The [public interface preview](https://henriquemayer.github.io/TuxedoFinance/)
remains a static tour without a login or persistence. Its disposable screenshot
database is managed by separate [preview tooling](../.github/preview/README.md).
`insert_demo` creates editable records in the selected local installation; it
does not publish them or bundle a runtime database in the repository.
