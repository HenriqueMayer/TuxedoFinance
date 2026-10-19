# Test layout

Run commands from the repository root. The [contributor guide](../CONTRIBUTING.md)
owns setup, isolation and validation instructions; this index explains where to
find a case.

| Path | Responsibility |
|---|---|
| `<app>/tests/test_*.py` | Django domain, ownership, model, service and rendered-response checks grouped by responsibility inside the owning app. |
| `<app>/tests/fixtures.py`, `factories.py`, `samples.py`, `snapshots.py`, `queries.py` | Reusable test setup and evidence helpers; only the files needed by each app exist. These modules are not test-discovery entry points. |
| `e2e/banking/` | Accounts, cards, invoices, loyalty, exchange rates and internal bank workspaces. |
| `e2e/categories/` | Category forms, filters and hierarchy integrity. |
| `e2e/dashboard/` | Authenticated Home, reports, period controls and source return context. |
| `e2e/investments/` | Setup, positions, operations, prices and investment valuation. |
| `e2e/planning/` | Budgets, goals, planning tools, scenarios and simulations. |
| `e2e/transactions/` | Transaction forms, lists, splits, payment selection and export. |
| `e2e/ingestion/` | Paused-import gates and owned read-only import history. |
| `e2e/assistant/` | Local history, responsive panel, draft continuity, session privacy, native fallback and streaming with an explicitly selected synthetic provider; no live provider. |
| `e2e/assistant_mock_settings.py` | Runner-guarded synthetic catalogue/streaming settings; accepts only an owned disposable runtime and blocks external network, OAuth and inference transports. |
| `e2e/catalogue/` | Design Lab components and local interactions using synthetic specimens. |
| `e2e/shared/` | Cross-workspace contracts, authentication/public pages, history, keyboard behavior and shared UI. |
| `e2e/helpers/` | Shared form/navigation actions, repository path resolution and bounded catalogue routing. |
| `preview/` | Static bilingual tour tests and their independent Playwright configuration. |
| `tooling/` | Standard-library Python tests for repository commands and dependency-free JavaScript amount/allocation tests. |

Documentation checks run with `uv run python scripts/check_docs.py` and are
covered by `tooling/test_check_docs.py`. They validate source paths, local
section anchors and legacy links without accessing installation data or the
network.

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
npm run test:e2e -- --assistant-fixtures tests/e2e/assistant/streaming.spec.js
npm run test:preview
```

The ordinary runner keeps real authorization/inference gates off and discards
inherited assistant settings. `--assistant-fixtures` explicitly selects
`e2e/assistant_mock_settings.py` for the native disposable runner only; it refuses
Docker mode and any path outside its owned temporary runtime/empty environment
file. The model catalogue and responses are synthetic, credentials are neither
read nor created, and external sockets/provider transports are blocked. Do not
select that settings module manually for an installation. These browser cases
verify UI/lifecycle behavior, not real account eligibility, quota or model quality.

For Django tests, use the isolated environment in the contributor guide. Within
that environment, `uv run python manage.py test banking` selects an app, and
`uv run python manage.py test banking.tests.test_cards_invoices` selects a
responsibility. Every app's `tests/__init__.py` stays free of test-class exports;
unittest discovers the `test_*.py` modules once. Import fixtures from their
explicit support module rather than importing another test module. Shared
ledger write classification lives in `transactions.tests.queries` and is also
used by dashboard read-model tests.

When code moves, patch the module where the dependency is looked up. For
example, invoice views use `banking.views.invoices.sync_user_ledger`, while bank
workspaces use `banking.views.workspace.sync_user_ledger`. Public view/form
package exports preserve application imports; they do not proxy mutable globals.
Compare discovered app/class/method identities when regrouping tests, preserving
assertions, decorators, native fallback and ownership coverage.

When regrouping specs, preserve the test inventory and assertions, update
relative imports, and use `helpers/paths.js` for repository files. Catalogue
cases reuse `helpers/catalogue.js` rather than adding a private file router.
Native fallback, real keyboard events and invalid-response coverage remain
part of the [form contract](../docs/frontend/forms.md#keyboard-and-choice-contract).

New diagnostics live under ignored `.local/`. Playwright may clear only its
dedicated browser-output directory; active disposable runtime and persistent
server logs remain outside that directory. Existing root artifacts and
installation files are not migration inputs and must not be removed.
