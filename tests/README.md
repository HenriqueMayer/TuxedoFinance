# Test layout

Run commands from the repository root. The [contributor guide](../CONTRIBUTING.md)
owns setup, isolation and validation instructions; this index explains where to
find a case.

| Path | Responsibility |
|---|---|
| `<app>/tests.py`, `<app>/test_*.py` | Django domain, ownership, model, service and rendered-response checks beside the owning app. |
| `e2e/banking/` | Accounts, cards, invoices, loyalty, exchange rates and internal bank workspaces. |
| `e2e/categories/` | Category forms, filters and hierarchy integrity. |
| `e2e/dashboard/` | Authenticated Home, reports, period controls and source return context. |
| `e2e/investments/` | Setup, positions, operations, prices and investment valuation. |
| `e2e/planning/` | Budgets, goals, planning tools, scenarios and simulations. |
| `e2e/transactions/` | Transaction forms, lists, splits, payment selection and export. |
| `e2e/ingestion/` | Paused-import gates and owned read-only import history. |
| `e2e/catalogue/` | Design Lab components and local interactions using synthetic specimens. |
| `e2e/shared/` | Cross-workspace contracts, authentication/public pages, history, keyboard behavior and shared UI. |
| `e2e/helpers/` | Shared form/navigation actions, repository path resolution and bounded catalogue routing. |
| `preview/` | Static bilingual tour tests and their independent Playwright configuration. |
| `tooling/` | Standard-library Python tests for repository commands and dependency-free JavaScript amount/allocation tests. |

The explicit application configuration is `tests/playwright.config.js`.
`npm run test:e2e` loads it through the disposable runner, which owns its server
and database. Never substitute a personal installation URL. The separate
`tests/preview/playwright.config.js` serves only the committed static tour.

Examples:

```bash
npm run test:unit
npm run test:e2e -- --list
npm run test:e2e -- tests/e2e/banking
npm run test:e2e -- tests/e2e/catalogue
npm run test:preview
```

When regrouping specs, preserve the test inventory and assertions, update
relative imports, and use `helpers/paths.js` for repository files. Catalogue
cases reuse `helpers/catalogue.js` rather than adding a private file router.
Native fallback, real keyboard events and invalid-response coverage remain
part of the [form contract](../docs/frontend.md#keyboard-and-choice-contract).

New diagnostics live under ignored `.local/`. Playwright may clear only its
dedicated browser-output directory; active disposable runtime and persistent
server logs remain outside that directory. Existing root artifacts and
installation files are not migration inputs and must not be removed.
